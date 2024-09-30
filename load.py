import logging
import os
import re
import zipfile
import traceback
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta, UTC
from semantic_version import Version
from pathlib import Path
from tempfile import gettempdir

# EDMC imports
from config import appname, appversion
from theme import theme


# plugin_name *must* be the plugin's folder name
plugin_name = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f'{appname}.{plugin_name}')
if not logger.hasHandlers():
    level = logging.INFO
    logger.setLevel(level)
    logger_channel = logging.StreamHandler()
    logger_formatter = logging.Formatter(f'%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d:%(funcName)s: %(message)s')
    logger_formatter.default_time_format = '%Y-%m-%d %H:%M:%S'
    logger_formatter.default_msec_format = '%s.%03d'
    logger_channel.setFormatter(logger_formatter)
    logger.addHandler(logger_channel)


plugin_location: Path | None = None

def plugin_start3(plugin_dir: str) -> str:
    global plugin_location
    plugin_location = Path(plugin_dir)
    return plugin_name


class MessageLabel(tk.Label):
    def __init__(self, parent):
        self.__var = tk.StringVar(value="Готов к сбору")
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
        self.__after_id = self.after(30*1000, lambda:self.__var.set("Готов к сбору"))


class PluginFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)

        self.button = ttk.Button(
            self,
            padding=5,
            text="Собрать логи в ZIP",
        )
        self.black_button = tk.Label(
            self,
            padx=5,
            pady=5,
            text="Собрать логи в ZIP"
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
        self.message_label.text = "Сбор логов..."
        logger.debug("Collecting log files...")

        try:
            logs = list()
            tempdir = Path(gettempdir())
            now = datetime.now(UTC)

            # Приколюхи от EDMC: в зависимости от версии, appversion может быть либо str,
            # либо ФУНКЦИЕЙ, возвращающей semantic_version.Version
            if isinstance(appversion, str):
                edmc_version = Version(appversion)
            elif callable(appversion):
                edmc_version = appversion()
            else:
                raise RuntimeError("wtf is this edmc version")

            if edmc_version < Version("5.12.0"):
                logs.append(tempdir/"EDMarketConnector.log")
                edmc_logs_dir = tempdir/"EDMarketConnector"       
            else:
                # линуксоиды, простите
                edmc_logs_dir = Path.home()/"AppData"/"Local"/"EDMarketConnector"/"logs"
            
            for logfile in (_ for _ in edmc_logs_dir.iterdir() if _.is_file()):
                edited_at = datetime.fromtimestamp(logfile.stat().st_mtime, tz=UTC)
                diff = now - edited_at
                if diff <= timedelta(hours=24):
                    logs.append(logfile)

            game_logs_dir = Path.home()/"Saved Games"/"Frontier Developments"/"Elite Dangerous"
            game_logs_pattern = re.compile(r"^Journal\.20\d{2}-\d{2}-\d{2}T\d{6}\.\d{2}\.log$")
            game_logs = [item for item in game_logs_dir.iterdir() if item.is_file() and re.match(game_logs_pattern, str(item.name)) is not None]
            for logfile in game_logs:
                edited_at = datetime.fromtimestamp(logfile.stat().st_mtime, tz=UTC)
                diff = now - edited_at
                if diff <= timedelta(hours=24):
                    logs.append(logfile)

            logger.debug(f"got list of logs: {logs}")

            output_dir = tempdir/"EDMC-LogCollector"
            output_dir.mkdir(exist_ok=True)

            ouput_zip_path = output_dir/"Triumvirate-logs.zip"
            with zipfile.ZipFile(ouput_zip_path, 'w') as zip:
                for file in logs:
                    name = file.name
                    zip.write(file, arcname=name)
            
            logger.debug("logs collected, opening explorer")
            self.message_label.text = "Логи собраны"

            os.system(f'explorer /select,\"{ouput_zip_path}\"')

        except:
            self.message_label.text = "Ошибка при сборе. Напишите @elcylite в Discord."
            logger.error(traceback.format_exc())



def plugin_app(parent: tk.Frame):
    return PluginFrame(parent)


def plugin_stop():
    logger.info("See You, Space Cowboy.")