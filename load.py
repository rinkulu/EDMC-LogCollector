import logging
import os
import platform
import re
import requests
import subprocess
import zipfile
import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta, UTC
from semantic_version import Version
from pathlib import Path
from tempfile import gettempdir
from threading import Thread
from typing import Any

# EDMC imports
from config import appname, appversion  # type: ignore
from config import config as edmc_config  # type: ignore
from theme import theme  # type: ignore
from ttkHyperlinkLabel import HyperlinkLabel  # type: ignore


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


class PluginConfig:
    """A simple wrapper around edmc_config for automatic addition of keys prefix."""
    def set(self, key: str, value: Any):
        return edmc_config.set(f"LogCollector-{key}", value)

    def delete(self, key: str, *, suppress=False):
        return edmc_config.delete(f"LogCollector-{key}", suppress=suppress)

    def get(self, key: str, default=None):
        return edmc_config.get(f"LogCollector-{key}", default=default)

    def get_str(self, key: str, default="") -> str:
        return edmc_config.get_str(f"LogCollector-{key}", default=default)

    def get_int(self, key: str, default=0) -> int:
        return edmc_config.get_int(f"LogCollector-{key}", default=default)

    def get_bool(self, key: str, default=False) -> bool:
        return edmc_config.get_bool(f"LogCollector-{key}", default=default)

    def get_list(self, key: str, default=None):
        return edmc_config.get_list(f"LogCollector-{key}", default=default)


plugin_config = PluginConfig()


class Prefs:
    def __init__(self):
        self.include_edmc_logs: bool
        self.include_journals: bool
        self.range_h: int
        self.load_saved()

    def load_saved(self):
        def _get_config(key, default):
            value = plugin_config.get(f"{key}", default=None)
            if value is None:
                logger.debug(f"Preference '{key}' not set, defaulting to {default}")
                value = default
                plugin_config.set(key, default)
            return value

        self.include_edmc_logs = bool(_get_config("include_edmc_logs", True))
        self.include_journals = bool(_get_config("include_journals", True))
        self.range_h = int(_get_config("range_h", 48))

    def save(self):
        logger.debug(f"Prefs saved: {self.dump()}")
        plugin_config.set("include_edmc_logs", self.include_edmc_logs)
        plugin_config.set("include_journals", self.include_journals)
        plugin_config.set("range_h", self.range_h)

    def dump(self):
        return {
            "include_edmc_logs": self.include_edmc_logs,
            "include_journals": self.include_journals,
            "range_h": self.range_h,
        }


prefs = Prefs()


class MessageLabel(tk.Label):
    DEFAULT_TEXT = _translate("Ready")

    def __init__(self, parent: tk.Widget):
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


class DarkCheckbutton(tk.Frame):
    """
    Born out of pure hatred towards EDMC theme support.
    `ttk.Checkbutton`s are not natively supported, just like buttons,
    so we have to use this messy thing instead.
    #FIX_YOUR_CODE_EDCD
    """
    def __init__(self, parent: tk.Widget, variable: tk.BooleanVar, text: str):
        super().__init__(parent)
        self._var = variable
        self._var.trace_add('write', self.__on_var_change)
        self.checkbox = tk.Label(self)
        self.label = tk.Label(self, text=text)
        self.__on_var_change()  # force checkbox text update
        theme.button_bind(self.checkbox, self.__on_click)
        self.checkbox.grid(row=0, column=0)
        self.label.grid(row=0, column=1)

    def __on_var_change(self, *args):
        if self._var.get():
            self.checkbox.configure(text='\u2611')
        else:
            self.checkbox.configure(text='\u2610')

    def __on_click(self, event: tk.Event):
        self._var.set(not self._var.get())


class PrefsFrame(tk.Frame):
    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)
        self.include_edmc_logs_var = tk.BooleanVar(value=prefs.include_edmc_logs)
        self.include_journals_var = tk.BooleanVar(value=prefs.include_journals)
        self.range_var = tk.IntVar(value=prefs.range_h)

        self.include_edmc_logs_checkbox = ttk.Checkbutton(
            self, variable=self.include_edmc_logs_var, text=_translate("Include EDMC logs")
        )
        self.include_edmc_logs_checkbox_dark = DarkCheckbutton(
            self, variable=self.include_edmc_logs_var, text=_translate("Include EDMC logs")
        )
        theme.register_alternate(
            (self.include_edmc_logs_checkbox, self.include_edmc_logs_checkbox_dark, self.include_edmc_logs_checkbox_dark),
            {"row": 0, "sticky": "NWS"}
        )

        self.include_journals_checkbox = ttk.Checkbutton(
            self, variable=self.include_journals_var, text=_translate("Include game journals")
        )
        self.include_journals_checkbox_dark = DarkCheckbutton(
            self, variable=self.include_journals_var, text=_translate("Include game journals")
        )
        theme.register_alternate(
            (self.include_journals_checkbox, self.include_journals_checkbox_dark, self.include_journals_checkbox_dark),
            {"row": 1, "sticky": "NWS"}
        )

        self.range_label = tk.Label(self, text=_translate("Range (hours):"))
        self.range_label.grid(row=2, sticky="NWS")
        self.range_scale = tk.Scale(self, variable=self.range_var, from_=12, to=120, tickinterval=12, orient=tk.HORIZONTAL)
        self.range_scale.grid(row=3, sticky="NWSE")


class PluginFrame(tk.Frame):
    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.grid_columnconfigure(0, weight=1)

        text = _translate("Collect and pack logs")
        self.collect_button = ttk.Button(self, text=text, padding=5)
        self.collect_button_dark = tk.Label(self, text=text, padx=5, pady=5)
        theme.register_alternate(
            (self.collect_button, self.collect_button_dark, self.collect_button_dark),
            {"row": 0, "column": 0, "columnspan": 2, "sticky": "NWSE"}
        )
        self.collect_button.bind('<Button-1>', self.collect_logs)
        theme.button_bind(self.collect_button_dark, self.collect_logs)

        self.message_label = MessageLabel(self)
        self.message_label.grid(row=1, column=0, sticky="NWS")

        self.prefs_opened = False

        self.open_prefs_button = ttk.Button(self, text="\u25bc", width=0)  # a small hack to prevent it from taking too much space
        self.open_prefs_button_dark = tk.Label(self, text="\u25bc")
        theme.register_alternate(
            (self.open_prefs_button, self.open_prefs_button_dark, self.open_prefs_button_dark),
            {"row": 1, "column": 1, "sticky": "NES"}
        )
        self.open_prefs_button.bind('<Button-1>', self.change_prefs_visability)
        theme.button_bind(self.open_prefs_button_dark, self.change_prefs_visability)

        self.prefs_frame = PrefsFrame(self)
        # we don't need to map it now, this will be done on `open_prefs_button` click

        self.update_label: HyperlinkLabel
        Thread(name="EDMC LogCollector updater", target=self.__check_updates).start()


    def collect_logs(self, event: tk.Event):
        self.message_label.text = _translate("Collection in process...")

        prefs.include_edmc_logs = self.prefs_frame.include_edmc_logs_var.get()
        prefs.include_journals = self.prefs_frame.include_journals_var.get()
        prefs.range_h = self.prefs_frame.range_var.get()
        prefs.save()

        logger.debug("Collecting log files...")
        try:
            logs = list()
            tempdir = Path(gettempdir())

            if prefs.include_edmc_logs:
                logs += self._collect_edmc_logs(tempdir)
            if prefs.include_journals:
                logs += self._collect_journals()

            if not logs:
                logger.debug(f"No suitable files found. Prefs: {prefs.dump()}")
                self.message_label.text = _translate("No suitable files found. Try changing the settings.")
                return

            logger.debug(f"Collected files: {', '.join(map(str, logs))}")

            output_dir = tempdir / "EDMC-LogCollector"
            output_dir.mkdir(exist_ok=True)
            ouput_zip_path = output_dir / "Triumvirate-logs.zip"
            with zipfile.ZipFile(ouput_zip_path, 'w') as zip:
                for file in logs:
                    name = file.name
                    zip.write(file, arcname=name)
            logger.debug("Logs are packed, opening explorer")
            self.message_label.text = _translate("Success. Opening ZIP location.")
            match system:
                case "Windows": os.system(f'explorer /select,\"{ouput_zip_path}\"')
                case "Darwin": subprocess.Popen(["open", str(output_dir)])
                case _: subprocess.Popen(["xdg-open", str(output_dir)])

        except Exception as e:
            self.message_label.text = _translate("An unexpected error occurred. Please report this issue to @elcylite on Discord.")
            logger.error("Unexpected error:", exc_info=e)


    def _collect_edmc_logs(self, tempdir: Path):
        now = datetime.now(UTC)
        logs = []
        # depending on EDMC version, appversion can be a string or a function returning semantic_version.Version
        if isinstance(appversion, str):
            edmc_version = Version(appversion)
        elif callable(appversion):
            edmc_version: Version = appversion()  # type: ignore
        else:
            # shouldn't really ever happen
            self.message_label.text = _translate("Failed to determine EDMC version. Please report this issue to @elcylite on Discord.")
            raise RuntimeError(f"Failed to determine EDMC version. appversion type: {type(appversion)}, value: {appversion}")

        if edmc_version <= Version("5.11.3"):
            logs.append(tempdir / "EDMarketConnector.log")
            edmc_logs_dir = tempdir / "EDMarketConnector"
        else:
            # the same way EDMC does this in its prefs.py
            edmc_logs_dir: Path = edmc_config.app_dir_path / "logs"

        for entry in edmc_logs_dir.iterdir():
            if entry.is_file():
                logs.append(entry)

        return [
            item for item in logs
            if (now - datetime.fromtimestamp(item.stat().st_mtime, tz=UTC)) < timedelta(hours=prefs.range_h)
        ]


    def _collect_journals(self):
        now = datetime.now(UTC)
        journal_dir = (
            Path(saved) if (saved := edmc_config.get_str("journaldir"))
            else Path.home() / "Saved Games" / "Frontier Developments" / "Elite Dangerous"
        )
        journal_pattern = re.compile(r"^Journal\.20\d{2}-\d{2}-\d{2}T\d{6}\.\d{2}\.log$")
        journals = [
            item for item in journal_dir.iterdir()
            if item.is_file()
            and re.match(journal_pattern, item.name) is not None
            and (now - datetime.fromtimestamp(item.stat().st_mtime, tz=UTC)) < timedelta(hours=prefs.range_h)
        ]
        return journals


    def change_prefs_visability(self, event: tk.Event):
        if self.prefs_opened:
            self.open_prefs_button.configure(text='\u25bc')
            self.open_prefs_button_dark.configure(text='\u25bc')
            self.prefs_frame.grid_forget()
            self.prefs_opened = False
            prefs.include_edmc_logs = self.prefs_frame.include_edmc_logs_var.get()
            prefs.include_journals = self.prefs_frame.include_journals_var.get()
            prefs.range_h = self.prefs_frame.range_var.get()
            prefs.save()
        else:
            self.open_prefs_button.configure(text='\u25b2')
            self.open_prefs_button_dark.configure(text='\u25b2')
            self.prefs_frame.grid(row=2, column=0, columnspan=2, sticky="NWSE")
            self.prefs_opened = True


    def __check_updates(self):
        def show_label(url: str):
            self.update_label = HyperlinkLabel(
                master=self,
                text=_translate("Update available: {ver}").format(ver=str(latest_version)),
                url=resp.json()["html_url"],
            )
            theme.update(self.update_label)
            self.update_label.grid(row=3, column=0, columnspan=2, sticky="NWSE")

        try:
            resp = requests.get("https://api.github.com/repos/rinkulu/EDMC-LogCollector/releases/latest")
            resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to check for updates:", exc_info=e)
            return
        latest_version = Version(resp.json()["tag_name"])
        if latest_version == plugin_version:
            logger.debug("Running the latest version.")
        else:
            logger.info(f"Found available update: {plugin_version} -> {latest_version}")
            self.after_idle(show_label, resp.json()["html_url"])


def plugin_start3(plugin_dir: str) -> str:
    global plugin_location
    plugin_location = Path(plugin_dir)
    logger.debug(f"Version {plugin_version}.")
    return f"{plugin_name} v{plugin_version}"


def plugin_app(parent: tk.Widget) -> tk.Frame:
    return PluginFrame(parent)


def plugin_stop():
    logger.info("See You, Space Cowboy.")
