import logging
import os
import platform
import re
import subprocess
import zipfile
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta, UTC
from semantic_version import Version
from pathlib import Path
from tempfile import gettempdir

# EDMC imports
from config import appname, appversion  # type: ignore
from config import config as edmc_config  # type: ignore
from theme import theme  # type: ignore


# localization support
import l10n  # type: ignore
import functools
_translate = functools.partial(l10n.translations.tl, context=__file__)  # type: ignore


# plugin_name *must* be the plugin's folder name
plugin_name = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f'{appname}.{plugin_name}')
if not logger.hasHandlers():
    level = logging.INFO
    logger.setLevel(level)
    logger_channel = logging.StreamHandler()
    logger_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d:%(funcName)s: %(message)s')
    logger_formatter.default_time_format = '%Y-%m-%d %H:%M:%S'
    logger_formatter.default_msec_format = '%s.%03d'
    logger_channel.setFormatter(logger_formatter)
    logger.addHandler(logger_channel)


plugin_version = Version("0.2.0")
plugin_location: Path | None = None
system = platform.system()


def plugin_start3(plugin_dir: str) -> str:
    global plugin_location
    plugin_location = Path(plugin_dir)
    logger.debug(f"Version {plugin_version}.")
    return f"{plugin_name} v{plugin_version}"


class MessageLabel(tk.Label):
    DEFAULT_TEXT = _translate("Ready")

    def __init__(self, parent):
        self.__var = tk.StringVar(value=self.DEFAULT_TEXT)
        self.__after_id: str | None = None
        super().__init__(parent, textvariable=self.__var)

    @property
    def text(self) -> str:
        return self.__var.get()

    @text.setter
    def text(self, text: str):
        if self.__after_id is not None:
            self.after_cancel(self.__after_id)
        self.__var.set(text)
        self.__after_id = self.after(30 * 1000, lambda: self.__var.set(self.DEFAULT_TEXT))


class PluginFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)

        text = _translate("Collect log files and compress into ZIP")
        self.button = ttk.Button(
            self,
            padding=5,
            text=text
        )
        self.black_button = tk.Label(
            self,
            padx=5,
            pady=5,
            text=text
        )

        self.button.grid(row=0, sticky="NWSE")
        self.black_button.grid(row=0, sticky="NWSE")
        theme.register_alternate(
            (self.button, self.black_button, self.black_button),
            {"row": 0, "sticky": "NWSE"}
        )
        self.button.bind('<Button-1>', self.collect_logs)
        theme.button_bind(self.black_button, self.collect_logs)

        self.message_label = MessageLabel(self)
        self.message_label.grid(row=1, sticky="NWSE")


    def collect_logs(self, event: tk.Event):
        self.message_label.text = _translate("Collecting in process...")
        logger.debug("Collecting log files...")

        try:
            logs = list()
            tempdir = Path(gettempdir())
            now = datetime.now(UTC)

            ### 1: EDMC LOGS
            # depending on EDMC version, appversion can be a string or a function returning semantic_version.Version
            if isinstance(appversion, str):
                edmc_version = Version(appversion)
            elif callable(appversion):
                edmc_version = appversion()
            else:
                # shouldn't really ever happen
                self.message_label.text = _translate("Failed to determine EDMC version. Please notify the developer.")
                raise RuntimeError(f"Failed to determine EDMC version. appversion type: {type(appversion)}")

            if edmc_version < Version("5.12.0"):
                logs.append(tempdir / "EDMarketConnector.log")
                edmc_logs_dir = tempdir / "EDMarketConnector"
            else:
                # the same way EDMC does this in its prefs.py
                edmc_logs_dir: Path = edmc_config.app_dir_path / "logs"

            for entry in edmc_logs_dir.iterdir():
                if entry.is_file():
                    logs.append(entry)

            ### 2: GAME JOURNALS
            journal_dir = (
                Path(saved) if (saved := edmc_config.get_str("journaldir"))
                else Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
            )
            journal_pattern = re.compile(r"^Journal\.20\d{2}-\d{2}-\d{2}T\d{6}\.\d{2}\.log$")
            journals = [
                item for item in journal_dir.iterdir()
                if item.is_file() and re.match(journal_pattern, item.name) is not None
            ]
            for journal in journals:
                created_at = datetime.fromisoformat(journal.name[8:-7]).astimezone()    # making it aware using the local timezone
                diff = now - created_at
                if diff <= timedelta(hours=48):
                    logs.append(journal)

            logger.debug(f"Collected files: {', '.join(map(str, logs))}")

            ### 3: ZIP
            output_dir = tempdir / "EDMC-LogCollector"
            output_dir.mkdir(exist_ok=True)

            ouput_zip_path = output_dir / "Triumvirate-logs.zip"
            with zipfile.ZipFile(ouput_zip_path, 'w') as zip:
                for file in logs:
                    name = file.name
                    zip.write(file, arcname=name)

            logger.debug("logs collected, opening explorer")
            self.message_label.text = _translate("Success. Opening ZIP location")

            match system:
                case "Windows": os.system(f'explorer /select,\"{ouput_zip_path}\"')
                case "Darwin": subprocess.Popen(["open", str(output_dir)])
                case _: subprocess.Popen(["xdg-open", str(output_dir)])

        except Exception as e:
            self.message_label.text = _translate("An unexpected error occurred. Please report this issue to @elcylite on Discord.")
            logger.error("Unexpected error:", exc_info=e)



def plugin_app(parent: tk.Frame):
    return PluginFrame(parent)


def plugin_stop():
    logger.info("See You, Space Cowboy.")
