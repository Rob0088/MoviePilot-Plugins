import os
from asyncio import Semaphore, TaskGroup, run, to_thread
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytz
from aiofiles import open
from aiohttp import ClientSession
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.plugins.alist2strm.alist import AlistClient, AlistFile

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase


class Alist2StrmMy(_PluginBase):
    # 插件名称
    plugin_name = "Alist2Strm_MY"
    # 插件描述
    plugin_desc = "从alist生成strm。"
    # 插件图标
    plugin_icon = "https://github.com/yubanmeiqin9048/MoviePilot-Plugins/blob/main/icons/Alist.png"
    # 插件版本
    plugin_version = "1.2"
    # 插件作者
    plugin_author = "yubanmeiqin9048"
    # 作者主页
    author_url = "https://github.com/yubanmeiqin9048"
    # 插件配置项ID前缀
    plugin_config_prefix = "alist2strmmy_"
    # 加载顺序
    plugin_order = 32
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _url = ""
    _token = ""
    _source_dir = ""
    _target_dir = ""
    _sync_remote = False
    _once = False
    _path_replace = ""
    _cron = ""
    _scheduler = None
    _onlyonce = False
    _process_file_suffix = settings.RMT_SUBEXT + settings.RMT_MEDIAEXT
    _max_download_worker = None
    _max_list_worker = None

    processed_remote_paths_in_local = set()

    def init_plugin(self, config: dict = None) -> None:
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._url = config.get("url")
            self._token = config.get("token")
            self._source_dir = config.get("source_dir")
            self._sync_remote = config.get("sync_remote")
            self._target_dir = config.get("target_dir")
            self._cron = config.get("cron")
            self._path_replace = config.get("path_replace")
            self._max_download_worker = (
                int(config.get("max_download_worker"))
                if config.get("max_download_worker")
                else 3
            )
            self._max_list_worker = (
                int(config.get("max_list_worker"))
                if config.get("max_list_worker")
                else 32
            )
            self.__update_config()

        if self.get_state() or self._onlyonce:
            if self._onlyonce:
                self._scheduler = BackgroundScheduler(timezone=settings.TZ)
                self._scheduler.add_job(
                    self.alist2strm,
                    "date",
                    run_date=datetime.now(tz=pytz.timezone(settings.TZ))
                    + timedelta(seconds=3),
                )
                # 关闭一次性开关
                self._onlyonce = False
                if self._scheduler.get_jobs():
                    self._scheduler.print_jobs()
                    self._scheduler.start()
            self.__update_config()

    def alist2strm(self) -> None:
        run(self.__process())

    async def __process(self) -> None:
        def filter_func(remote_path: AlistFile) -> bool:
            if remote_path.is_dir:
                return False

            if remote_path.suffix.lower() not in self._process_file_suffix:
                logger.debug(f"文件 {remote_path.path} 不在处理列表中")
                return False

            local_path = self.__computed_target_path(remote_path)
            if self._sync_remote:
                self.processed_remote_paths_in_local.add(local_path)

            if local_path.exists():
                logger.debug(
                    f"文件 {local_path.name} 已存在，跳过处理 {remote_path.path}"
                )
                return False

            return True

        async with Semaphore(self._max_list_worker):
            async with AsyncExitStack() as stack:
                tg = await stack.enter_async_context(TaskGroup())
                client = await stack.enter_async_context(
                    AlistClient(url=self._url, token=self._token)
                )
                async for path in client.iter_path(
                    iter_dir=self._source_dir, filter_func=filter_func
                ):
                    logger.debug(f"处理 {path.path}")
                    tg.create_task(self.__to_strm(path))
        logger.info(f"{self._source_dir} 同步完成")

        if self._sync_remote:
            await self.__cleanup_invalid_strm()
            logger.info("清理过期的 .strm 文件完成")

    async def __to_strm(self, path: AlistFile) -> None:
        # 计算保存路径
        target_path = self.__computed_target_path(path)
        # strm内容
        content = path.download_url
        # 创建父目录
        if not target_path.parent.exists():
            await to_thread(target_path.parent.mkdir, parents=True, exist_ok=True)
        # 写入strm文件
        if target_path.suffix == ".strm":
            async with open(target_path, mode="w", encoding="utf-8") as file:
                await file.write(content)
        # 下载字幕文件
        elif target_path.suffix in settings.RMT_SUBEXT:
            async with Semaphore(self._max_download_worker):
                async with AsyncExitStack() as stack:
                    file = await stack.enter_async_context(open(target_path, mode="wb"))
                    logger.debug(f"下载字幕 {target_path}")
                    session = await stack.enter_async_context(ClientSession())
                    async with session.get(path.download_url) as resp:
                        if resp.status != 200:
                            raise RuntimeError(
                                f"下载 {path.download_url} 失败，状态码：{resp.status}"
                            )
                        chunk = await resp.read()
                        await file.write(chunk)

    async def __cleanup_invalid_strm(self) -> None:
        all_local_files = [f for f in Path(self._target_dir).rglob("*") if f.is_file()]
        files_need_to_delete = (
            set(all_local_files) - self.processed_remote_paths_in_local
        )
        for file_need_to_delete in files_need_to_delete:
            try:
                if file_need_to_delete.exists():
                    await to_thread(file_need_to_delete.unlink)
                    logger.info(f"删除文件：{file_need_to_delete}")
            except Exception as e:
                logger.error(f"删除文件 {file_need_to_delete} 失败：{e}")

    def __computed_target_path(self, path: AlistFile) -> Path:
        """
        计算strm文件保存路径。

        :param path: AlistPath 对象
        :return: 本地文件路径
        """
        target_path = Path(
            os.path.join(
                self._target_dir,
                path.path.replace(self._source_dir, self._path_replace, 1).lstrip("/"),
            )
        )

        if path.suffix.lower() in settings.RMT_MEDIAEXT:
            target_path = target_path.with_suffix(".strm")

        return target_path

    def __update_config(self) -> None:
        self.update_config(
            {
                "enabled": self._enabled,
                "onlyonce": False,
                "url": self._url,
                "token": self._token,
                "source_dir": self._source_dir,
                "sync_remote": self._sync_remote,
                "target_dir": self._target_dir,
                "cron": self._cron,
                "path_replace": self._path_replace,
                "max_download_worker": self._max_download_worker,
                "max_list_worker": self._max_list_worker,
            }
        )

    def get_state(self) -> bool:
        return (
            True
            if self._enabled and self._cron and self._token and self._url
            else False
        )

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        if self.get_state():
            return [
                {
                    "id": "IYUUAutoSeed",
                    "name": "全量生成STRM",
                    "trigger": CronTrigger.from_crontab(self._cron),
                    "func": self.alist2strm,
                    "kwargs": {},
                }
            ]
        return []

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return (
            [
                {
                    "component": "VForm",
                    "content": [
                        {
                            "component": "VRow",
                            "content": [
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VSwitch",
                                            "props": {
                                                "model": "enabled",
                                                "label": "启用插件",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VSwitch",
                                            "props": {
                                                "model": "onlyonce",
                                                "label": "立即运行一次",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VSwitch",
                                            "props": {
                                                "model": "sync_remote",
                                                "label": "失效清理",
                                            },
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "component": "VRow",
                            "content": [
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "url",
                                                "label": "alist地址",
                                                "placeholder": "http://localhost:2111",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "token",
                                                "label": "令牌",
                                                "placeholder": "token",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "cron",
                                                "label": "定时",
                                                "placeholder": "0 1 * * 3",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "source_dir",
                                                "label": "同步源根目录",
                                                "placeholder": "/source_path",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "target_dir",
                                                "label": "本地保存根目录",
                                                "placeholder": "/target_path",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "path_replace",
                                                "label": "路径替换",
                                                "placeholder": "/replace_path",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "max_list_worker",
                                                "label": "扫库线程",
                                            },
                                        }
                                    ],
                                },
                                {
                                    "component": "VCol",
                                    "props": {"cols": 12, "md": 4},
                                    "content": [
                                        {
                                            "component": "VTextField",
                                            "props": {
                                                "model": "max_download_worker",
                                                "label": "下载线程",
                                            },
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "component": "VRow",
                            "content": [
                                {
                                    "component": "VCol",
                                    "props": {
                                        "cols": 12,
                                    },
                                    "content": [
                                        {
                                            "component": "VAlert",
                                            "props": {
                                                "type": "info",
                                                "variant": "tonal",
                                                "text": "定期同步远端文件到本地strm",
                                            },
                                        }
                                    ],
                                }
                            ],
                        },
                    ],
                }
            ],
            {
                "enabled": False,
                "onlyonce": False,
                "sync_remote": False,
                "url": "",
                "cron": "",
                "token": "",
                "source_dir": "",
                "target_dir": "",
                "path_replace": None,
                "max_list_worker": None,
                "max_download_worker": None,
            },
        )

    def get_page(self) -> List[dict]:
        pass

    def stop_service(self) -> None:
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            logger.error("退出插件失败：%s" % str(e))
