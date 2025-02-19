import logging
import os
import re
import zipfile
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta, UTC
from semantic_version import Version
from pathlib import Path
from tempfile import gettempdir

# EDMC imports
from config import appname, appversion
from theme import theme


# localization support
import l10n
import functools
_translate = functools.partial(l10n.translations.tl, context=__file__)


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


    def collect_logs(self, event):
        self.message_label.text = _translate("Collecting in process...")
        logger.debug("Collecting log files...")

        try:
            logs = list()
            tempdir = Path(gettempdir())
            now = datetime.now(UTC)

            # depending on EDMC version, appversion can be a string or a function returning semantic_version.Version
            if isinstance(appversion, str):
                edmc_version = Version(appversion)
            elif callable(appversion):
                edmc_version = appversion()
            else:
                raise RuntimeError(f"Couldn't get EDMC version. appversion type: {type(appversion)}")

            if edmc_version < Version("5.12.0"):
                logs.append(tempdir / "EDMarketConnector.log")
                edmc_logs_dir = tempdir / "EDMarketConnector"
            else:
                # no support for linux yet bc i'm lazy
                edmc_logs_dir = Path.home() / "AppData" / "Local" / "EDMarketConnector" / "logs"

            for logfile in (_ for _ in edmc_logs_dir.iterdir() if _.is_file()):
                logs.append(logfile)

            game_logs_dir = Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
            game_logs_pattern = re.compile(r"^Journal\.20\d{2}-\d{2}-\d{2}T\d{6}\.\d{2}\.log$")
            game_logs = [
                item for item in game_logs_dir.iterdir()
                if item.is_file() and re.match(game_logs_pattern, item.name) is not None
            ]
            for logfile in game_logs:
                created_at = datetime.fromisoformat(logfile.name[8:-7]).astimezone()    # making it aware using the local timezone
                diff = now - created_at
                if diff <= timedelta(hours=48):
                    logs.append(logfile)

            logger.debug(f"got list of logs: {logs}")

            output_dir = tempdir / "EDMC-LogCollector"
            output_dir.mkdir(exist_ok=True)

            ouput_zip_path = output_dir / "Triumvirate-logs.zip"
            with zipfile.ZipFile(ouput_zip_path, 'w') as zip:
                for file in logs:
                    name = file.name
                    zip.write(file, arcname=name)

            logger.debug("logs collected, opening explorer")
            self.message_label.text = _translate("Success. Opening ZIP location")

            os.system(f'explorer /select,\"{ouput_zip_path}\"')

        except Exception as e:
            self.message_label.text = _translate("An unexpected error occurred. Please report this issue to @elcylite on Discord.")
            logger.error("An error during collecting the log files occured.", exc_info=e)



def plugin_app(parent: tk.Frame):
    import sys
    if sys.platform != "win32":
        return tk.Label("Sorry, EDMC-LogCollector is currently supported only on Windows.")
    return PluginFrame(parent)


def plugin_stop():
    logger.info("See You, Space Cowboy.")
