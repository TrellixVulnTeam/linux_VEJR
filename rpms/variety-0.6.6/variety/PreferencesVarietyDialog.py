# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# Copyright (c) 2012, Peter Levi <peterlevi@peterlevi.com>
# This program is free software: you can redistribute it and/or modify it 
# under the terms of the GNU General Public License version 3, as published 
# by the Free Software Foundation.
# 
# This program is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranties of 
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR 
# PURPOSE.  See the GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License along 
# with this program.  If not, see <http://www.gnu.org/licenses/>.
### END LICENSE

# This is the preferences dialog.

from gi.repository import Gtk, Gdk, GObject, GdkPixbuf # pylint: disable=E0611
import io
import stat

import threading
import subprocess
from variety.Util import Util
from variety import Texts
from variety.plugins.IQuoteSource import IQuoteSource
from variety_lib import varietyconfig
from variety_lib.varietyconfig import get_data_file
from variety.FolderChooser import FolderChooser
from variety.Options import Options
from variety.AddFlickrDialog import AddFlickrDialog
from variety.AddMediaRssDialog import AddMediaRssDialog
from variety.AddRedditDialog import AddRedditDialog
from variety.EditFavoriteOperationsDialog import EditFavoriteOperationsDialog
from variety.SmartFeaturesConfirmationDialog import SmartFeaturesConfirmationDialog
from variety.LoginOrRegisterDialog import LoginOrRegisterDialog
from variety.AddWallhavenDialog import AddWallhavenDialog

from variety import _, _u

import os
import logging
import random

random.seed()
logger = logging.getLogger('variety')

from variety_lib.PreferencesDialog import PreferencesDialog

UNREMOVEABLE_TYPES = [
    Options.SourceType.FAVORITES,
    Options.SourceType.FETCHED,
    Options.SourceType.DESKTOPPR,
    Options.SourceType.BING,
    Options.SourceType.UNSPLASH,
    Options.SourceType.APOD,
    Options.SourceType.EARTH,
    Options.SourceType.RECOMMENDED,
    Options.SourceType.LATEST,
]

EDITABLE_TYPES = [
    Options.SourceType.FLICKR,
    Options.SourceType.MEDIA_RSS,
    Options.SourceType.WALLHAVEN,
    Options.SourceType.REDDIT,
]


class PreferencesVarietyDialog(PreferencesDialog):
    __gtype_name__ = "PreferencesVarietyDialog"

    def finish_initializing(self, builder, parent): # pylint: disable=E1002
        """Set up the preferences dialog"""
        super(PreferencesVarietyDialog, self).finish_initializing(builder, parent)

        # Bind each preference widget to gsettings
        #        widget = self.builder.get_object('example_entry')
        #        settings.bind("example", widget, "text", Gio.SettingsBindFlags.DEFAULT)

        if Gdk.Screen.get_default().get_height() < 750:
            self.ui.sources_scrolled_window.set_size_request(0, 0)
            self.ui.hosts_scrolled_window.set_size_request(0, 0)
            self.ui.tips_scrolled_window.set_size_request(0, 0)

        PreferencesVarietyDialog.add_image_preview(self.ui.icon_chooser, 64)
        self.loading = False

        self.dl_chooser = FolderChooser(self.ui.download_folder_chooser, self.on_downloaded_changed)
        self.fav_chooser = FolderChooser(self.ui.favorites_folder_chooser, self.on_favorites_changed)
        self.fetched_chooser = FolderChooser(self.ui.fetched_folder_chooser, self.on_fetched_changed)
        self.copyto_chooser = FolderChooser(self.ui.copyto_folder_chooser, self.on_copyto_changed)
        self.slideshow_custom_chooser = FolderChooser(self.ui.slideshow_custom_chooser, self.delayed_apply)

        try:
            from varietyslideshow import varietyslideshow
        except:
            self.ui.notebook.remove_page(2)

        self.reload()

    def fill_smart_profile_url(self, msg):
        if '%SMART_PROFILE_URL%' in msg:
            profile_url = self.parent.smart.get_profile_url()
            msg = msg.replace('%SMART_PROFILE_URL%', profile_url) if profile_url else ""
        return msg

    def update_status_message(self):
        msg = ""
        if self.parent.server_options:
            try:
                msg_dict = self.parent.server_options.get("status_message", {})
                ver = varietyconfig.get_version()
                if ver in msg_dict:
                    msg = msg_dict[ver].strip()
                elif "*" in msg_dict:
                    msg = msg_dict["*"].strip()

                msg = self.fill_smart_profile_url(msg)
            except Exception:
                logger.exception(lambda: "Could not parse status message")
                msg = ""

        self.set_status_message(msg)

    def set_status_message(self, msg):
        def _update_ui():
            self.ui.status_message.set_visible(msg)
            self.ui.status_message.set_markup(msg)
        GObject.idle_add(_update_ui)

    def reload(self):
        try:
            logger.info(lambda: "Reloading preferences dialog")

            self.loading = True

            self.options = Options()
            self.options.read()

            self.ui.autostart.set_active(os.path.isfile(os.path.expanduser(u"~/.config/autostart/variety.desktop")))

            self.ui.change_enabled.set_active(self.options.change_enabled)
            self.set_change_interval(self.options.change_interval)
            self.ui.change_on_start.set_active(self.options.change_on_start)
            self.ui.safe_mode.set_active(self.options.safe_mode)

            self.ui.download_enabled.set_active(self.options.download_enabled)
            self.set_download_interval(self.options.download_interval)

            self.dl_chooser.set_folder(os.path.expanduser(self.options.download_folder))
            self.update_real_download_folder()

            self.ui.quota_enabled.set_active(self.options.quota_enabled)
            self.ui.quota_size.set_text(str(self.options.quota_size))

            self.fav_chooser.set_folder(os.path.expanduser(self.options.favorites_folder))

            self.fetched_chooser.set_folder(os.path.expanduser(self.options.fetched_folder))
            self.ui.clipboard_enabled.set_active(self.options.clipboard_enabled)
            self.ui.clipboard_use_whitelist.set_active(self.options.clipboard_use_whitelist)
            self.ui.clipboard_hosts.get_buffer().set_text('\n'.join(self.options.clipboard_hosts))

            if self.options.icon == "Light":
                self.ui.icon.set_active(0)
            elif self.options.icon == "Dark":
                self.ui.icon.set_active(1)
            elif self.options.icon == "Current":
                self.ui.icon.set_active(2)
            elif self.options.icon == "None":
                self.ui.icon.set_active(4)
            else:
                self.ui.icon.set_active(3)
                self.ui.icon_chooser.set_filename(self.options.icon)

            if self.options.favorites_operations == [["/", "Copy"]]:
                self.ui.favorites_operations.set_active(0)
            elif self.options.favorites_operations == [["/", "Move"]]:
                self.ui.favorites_operations.set_active(1)
            elif self.options.favorites_operations == [["/", "Both"]]:
                self.ui.favorites_operations.set_active(2)
            else:
                self.ui.favorites_operations.set_active(3)

            self.favorites_operations = self.options.favorites_operations

            self.ui.smart_enabled.set_active(self.options.smart_enabled)
            self.ui.sync_enabled.set_active(self.options.sync_enabled)
            self.ui.stats_enabled.set_active(self.options.stats_enabled)

            self.ui.facebook_show_dialog.set_active(self.options.facebook_show_dialog)

            self.ui.copyto_enabled.set_active(self.options.copyto_enabled)
            self.copyto_chooser.set_folder(self.parent.get_actual_copyto_folder())

            self.ui.desired_color_enabled.set_active(self.options.desired_color_enabled)
            self.ui.desired_color.set_color(Gdk.Color(red = 160 * 256, green = 160 * 256, blue = 160 * 256))
            c = self.options.desired_color
            if c:
                self.ui.desired_color.set_color(Gdk.Color(red = c[0] * 256, green = c[1] * 256, blue = c[2] * 256))

            self.ui.min_size_enabled.set_active(self.options.min_size_enabled)
            min_sizes = [50, 80, 100]
            index = 0
            while min_sizes[index] < self.options.min_size and index < len(min_sizes) - 1:
                index += 1
            self.ui.min_size.set_active(index)
            self.ui.landscape_enabled.set_active(self.options.use_landscape_enabled)
            self.ui.lightness_enabled.set_active(self.options.lightness_enabled)
            self.ui.lightness.set_active(0 if self.options.lightness_mode == Options.LightnessMode.DARK else 1)
            self.ui.min_rating_enabled.set_active(self.options.min_rating_enabled)
            self.ui.min_rating.set_active(self.options.min_rating - 1)
            self.ui.clock_enabled.set_active(self.options.clock_enabled)
            self.ui.clock_font.set_font_name(self.options.clock_font)
            self.ui.clock_date_font.set_font_name(self.options.clock_date_font)

            self.ui.quotes_enabled.set_active(self.options.quotes_enabled)
            self.ui.quotes_font.set_font_name(self.options.quotes_font)
            c = self.options.quotes_text_color
            self.ui.quotes_text_color.set_color(Gdk.Color(red = c[0] * 256, green = c[1] * 256, blue = c[2] * 256))
            c = self.options.quotes_bg_color
            self.ui.quotes_bg_color.set_color(Gdk.Color(red = c[0] * 256, green = c[1] * 256, blue = c[2] * 256))
            self.ui.quotes_bg_opacity.set_value(self.options.quotes_bg_opacity)
            self.ui.quotes_text_shadow.set_active(self.options.quotes_text_shadow)
            self.ui.quotes_tags.set_text(self.options.quotes_tags)
            self.ui.quotes_authors.set_text(self.options.quotes_authors)
            self.ui.quotes_change_enabled.set_active(self.options.quotes_change_enabled)
            self.set_quotes_change_interval(self.options.quotes_change_interval)
            self.ui.quotes_width.set_value(self.options.quotes_width)
            self.ui.quotes_hpos.set_value(self.options.quotes_hpos)
            self.ui.quotes_vpos.set_value(self.options.quotes_vpos)

            self.ui.slideshow_sources_enabled.set_active(self.options.slideshow_sources_enabled)
            self.ui.slideshow_favorites_enabled.set_active(self.options.slideshow_favorites_enabled)
            self.ui.slideshow_downloads_enabled.set_active(self.options.slideshow_downloads_enabled)
            self.ui.slideshow_custom_enabled.set_active(self.options.slideshow_custom_enabled)
            self.slideshow_custom_chooser.set_folder(os.path.expanduser(self.options.slideshow_custom_folder))

            if self.options.slideshow_sort_order == "Random":
                self.ui.slideshow_sort_order.set_active(0)
            elif self.options.slideshow_sort_order == "Name, asc":
                self.ui.slideshow_sort_order.set_active(1)
            elif self.options.slideshow_sort_order == "Name, desc":
                self.ui.slideshow_sort_order.set_active(2)
            elif self.options.slideshow_sort_order == "Date, asc":
                self.ui.slideshow_sort_order.set_active(3)
            elif self.options.slideshow_sort_order == "Date, desc":
                self.ui.slideshow_sort_order.set_active(4)
            else:
                self.ui.slideshow_sort_order.set_active(0)

            self.ui.slideshow_monitor.remove_all()
            self.ui.slideshow_monitor.append_text(_('All'))

            screen = Gdk.Screen.get_default()
            for i in range(0, screen.get_n_monitors()):
                geo = screen.get_monitor_geometry(i)
                self.ui.slideshow_monitor.append_text('%d - %s, %dx%d' % (i + 1, screen.get_monitor_plug_name(i), geo.width, geo.height))
            self.ui.slideshow_monitor.set_active(0)
            try:
                self.ui.slideshow_monitor.set_active(int(self.options.slideshow_monitor))
            except:
                self.ui.slideshow_monitor.set_active(0)

            if self.options.slideshow_mode == "Fullscreen":
                self.ui.slideshow_mode.set_active(0)
            elif self.options.slideshow_mode == "Desktop":
                self.ui.slideshow_mode.set_active(1)
            elif self.options.slideshow_mode == "Maximized":
                self.ui.slideshow_mode.set_active(2)
            elif self.options.slideshow_mode == "Window":
                self.ui.slideshow_mode.set_active(3)
            else:
                self.ui.slideshow_mode.set_active(0)

            self.ui.slideshow_seconds.set_value(self.options.slideshow_seconds)
            self.ui.slideshow_fade.set_value(self.options.slideshow_fade)
            self.ui.slideshow_zoom.set_value(self.options.slideshow_zoom)
            self.ui.slideshow_pan.set_value(self.options.slideshow_pan)

            self.ui.sources.get_model().clear()
            for s in self.options.sources:
                self.ui.sources.get_model().append(self.source_to_model_row(s))

            if not hasattr(self, "enabled_toggled_handler_id"):
                self.enabled_toggled_handler_id = self.ui.sources_enabled_checkbox_renderer.connect(
                        "toggled", self.source_enabled_toggled, self.ui.sources.get_model())
            #self.ui.sources.get_selection().connect("changed", self.on_sources_selection_changed)

            if hasattr(self, "filter_checkboxes"):
                for cb in self.filter_checkboxes:
                    self.ui.filters_grid.remove(cb)
                    cb.destroy()
            self.filter_checkboxes = []
            self.filter_name_to_checkbox = {}
            for i, f in enumerate(self.options.filters):
                cb = Gtk.CheckButton(Texts.FILTERS.get(f[1], f[1]))
                self.filter_name_to_checkbox[f[1]] = cb
                cb.connect("toggled", self.delayed_apply)
                cb.set_visible(True)
                cb.set_active(f[0])
                cb.set_margin_right(20)
                self.ui.filters_grid.attach(cb, i % 4, i // 4, 1, 1)
                self.filter_checkboxes.append(cb)

            if hasattr(self, "quotes_sources_checkboxes"):
                for cb in self.quotes_sources_checkboxes:
                    self.ui.quotes_sources_grid.remove(cb)
                    cb.destroy()
            self.quotes_sources_checkboxes = []
            for i, p in enumerate(self.parent.jumble.get_plugins(IQuoteSource)):
                cb = Gtk.CheckButton(p['info']['name'])
                cb.connect("toggled", self.delayed_apply)
                cb.set_visible(True)
                cb.set_tooltip_text(p['info']['description'])
                cb.set_active(p['info']['name'] not in self.options.quotes_disabled_sources)
                cb.set_margin_right(20)
                self.ui.quotes_sources_grid.attach(cb, i % 4, i // 4, 1, 1)
                self.quotes_sources_checkboxes.append(cb)

            self.ui.tips_buffer.set_text('\n\n'.join(Texts.TIPS))

            try:
                with io.open(get_data_file("ui/changes.txt")) as f:
                    self.ui.changes_buffer.set_text(f.read())
            except Exception:
                logger.warning(lambda: "Missing ui/changes.txt file")

            self.on_smart_user_updated()

            self.on_change_enabled_toggled()
            self.on_download_enabled_toggled()
            self.on_sources_selection_changed()
            self.on_desired_color_enabled_toggled()
            self.on_min_size_enabled_toggled()
            self.on_lightness_enabled_toggled()
            self.on_min_rating_enabled_toggled()
            self.on_copyto_enabled_toggled()
            self.on_quotes_change_enabled_toggled()
            self.on_icon_changed()
            self.on_favorites_operations_changed()
            self.update_clipboard_state()

            self.build_add_button_menu()

            self.update_status_message()
        finally:
            # To be sure we are completely loaded, pass via two hops: first delay, then idle_add:
            def _finish_loading():
                self.loading = False
            def _idle_finish_loading():
                GObject.idle_add(_finish_loading)
            timer = threading.Timer(1, _idle_finish_loading)
            timer.start()

    def on_add_button_clicked(self, widget=None):
        def position(*args, **kwargs):
            button_alloc = self.ui.add_button.get_allocation()
            window_pos = self.ui.add_button.get_window().get_position()
            return button_alloc.x + window_pos[0], button_alloc.y + button_alloc.height + window_pos[1], True

        self.add_menu.popup(None, self.ui.add_button, position, None, 0, Gtk.get_current_event_time())

    def on_remove_sources_clicked(self, widget=None):
        def position(*args, **kwargs):
            button_alloc = self.ui.remove_sources.get_allocation()
            window_pos = self.ui.remove_sources.get_window().get_position()
            return button_alloc.x + window_pos[0], button_alloc.y + button_alloc.height + window_pos[1], True

        self.build_remove_button_menu().popup(None, self.ui.remove_sources, position, None, 0, Gtk.get_current_event_time())

    def build_add_button_menu(self):
        self.add_menu = Gtk.Menu()

        items = [
            (_("Images"), self.on_add_images_clicked),
            (_("Folders"), self.on_add_folders_clicked),
            '-',
            (_("Flickr"), self.on_add_flickr_clicked),
            (_("Wallhaven.cc"), self.on_add_wallhaven_clicked),
            (_("Reddit"), self.on_add_reddit_clicked),
            (_("Media RSS"), self.on_add_mediarss_clicked),
        ]

        for x in items:
            if x == '-':
                item = Gtk.SeparatorMenuItem.new()
            else:
                item = Gtk.MenuItem()
                item.set_label(x[0])
                item.connect("activate", x[1])
            self.add_menu.append(item)

        self.add_menu.show_all()

    def build_remove_button_menu(self):
        model, rows = self.ui.sources.get_selection().get_selected_rows()

        has_downloaders = False
        for row in rows:
            type = Options.str_to_type(model[row][1])
            if type in Options.SourceType.dl_types and type not in UNREMOVEABLE_TYPES:
                has_downloaders = True

        self.remove_menu = Gtk.Menu()
        item1 = Gtk.MenuItem()
        item1.set_label(_("Remove the source, keep the files") if len(rows) == 1 else
            _("Remove the sources, keep the files"))
        item1.connect("activate", self.remove_sources)
        self.remove_menu.append(item1)

        item2 = Gtk.MenuItem()
        def _remove_with_files(widget=None):
            self.remove_sources(delete_files=True)
        item2.set_label(_("Remove the source and delete the downloaded files") if len(rows) == 1 else
            _("Remove the sources and delete the downloaded files"))
        item2.connect("activate", _remove_with_files)
        item2.set_sensitive(has_downloaders)
        self.remove_menu.append(item2)

        self.remove_menu.show_all()
        return self.remove_menu

    def source_enabled_toggled(self, widget, path, model):
        row = model[path]
        row[0] = not row[0]
        self.on_row_enabled_state_changed(row)

    def on_row_enabled_state_changed(self, row):
        # Special case when enabling the Earth downloader:
        if row[0] and row[1] == Options.type_to_str(Options.SourceType.EARTH):
            updated = False
            if not self.ui.change_enabled.get_active():
                self.ui.change_enabled.set_active(True)
                updated = True
            if self.get_change_interval() > 30 * 60:
                self.set_change_interval(30 * 60)
                updated = True

            if not self.ui.download_enabled.get_active():
                self.ui.download_enabled.set_active(True)
                updated = True
            if self.get_download_interval() > 30 * 60:
                self.set_download_interval(30 * 60)
                updated = True

            if updated:
                self.parent.show_notification(
                    _("World Sunlight Map enabled"),
                    _("Using the World Sunlight Map requires both downloading and changing "
                    "enabled at intervals of 30 minutes or less. Settings were adjusted automatically."))

        # special case when enabling the Recommended or Latest downloader:
        elif row[0] and row[1] in (Options.type_to_str(Options.SourceType.RECOMMENDED),) and \
                not self.parent.options.smart_enabled:

            row[0] = False
            self.dialog = SmartFeaturesConfirmationDialog()
            def _on_ok(button):
                self.parent.options.smart_enabled = self.dialog.ui.smart_enabled.get_active()
                self.parent.options.write()
                self.ui.smart_enabled.set_active(self.parent.options.smart_enabled)
                if self.parent.options.smart_enabled:
                    row[0] = True

            self.dialog.ui.btn_ok.connect("clicked", _on_ok)
            self.dialog.run()
            self.dialog.destroy()
            self.dialog = None

    def set_time(self, interval, text, time_unit, times=(1, 60, 60 * 60, 24 * 60 * 60)):
        if interval < 5:
            interval = 5
        x = len(times) - 1
        while times[x] > interval:
            x -= 1
        text.set_text(str(interval // times[x]))
        time_unit.set_active(x)
        return

    def set_change_interval(self, seconds):
        self.set_time(seconds, self.ui.change_interval_text, self.ui.change_interval_time_unit)

    def set_download_interval(self, seconds):
        self.set_time(seconds, self.ui.download_interval_text, self.ui.download_interval_time_unit,
                      times=(60, 60 * 60, 24 * 60 * 60))

    def set_quotes_change_interval(self, seconds):
        self.set_time(seconds, self.ui.quotes_change_interval_text, self.ui.quotes_change_interval_time_unit)

    def read_time(self, text_entry, time_unit_combo, minimum, default):
        result = default
        try:
            interval = int(text_entry.get_text())
            tree_iter = time_unit_combo.get_active_iter()
            if tree_iter:
                model = time_unit_combo.get_model()
                time_unit_seconds = model[tree_iter][1]
                result = interval * time_unit_seconds
                if result < minimum:
                    result = minimum
        except Exception:
            logger.exception(lambda: "Could not understand interval")
        return result

    def get_change_interval(self):
        return self.read_time(
            self.ui.change_interval_text, self.ui.change_interval_time_unit, 5, self.options.change_interval)

    def get_download_interval(self):
        return self.read_time(
            self.ui.download_interval_text, self.ui.download_interval_time_unit, 60, self.options.download_interval)

    def get_quotes_change_interval(self):
        return self.read_time(
            self.ui.quotes_change_interval_text, self.ui.quotes_change_interval_time_unit, 10, self.options.quotes_change_interval)

    @staticmethod
    def add_image_preview(chooser, size = 250):
        preview = Gtk.Image()
        chooser.set_preview_widget(preview)

        def update_preview(c):
            try:
                file = chooser.get_preview_filename()
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(file, size, size)
                preview.set_from_pixbuf(pixbuf)
                chooser.set_preview_widget_active(True)
            except Exception:
                chooser.set_preview_widget_active(False)

        chooser.connect("update-preview", update_preview)

    def on_add_images_clicked(self, widget=None):
        chooser = Gtk.FileChooserDialog(_("Add Images"), parent=self, action=Gtk.FileChooserAction.OPEN,
            buttons=[_("Cancel"), Gtk.ResponseType.CANCEL, _("Add"), Gtk.ResponseType.OK])
        self.dialog = chooser
        PreferencesVarietyDialog.add_image_preview(chooser)
        chooser.set_select_multiple(True)
        chooser.set_local_only(True)
        filter = Gtk.FileFilter()
        filter.set_name(_("Images"))
        for s in ["jpg", "jpeg", "png", "bmp", "tiff", "svg"]:
            filter.add_pattern("*." + s)
            filter.add_pattern("*." + s.upper())
        chooser.add_filter(filter)
        response = chooser.run()

        if response == Gtk.ResponseType.OK:
            images = list(chooser.get_filenames())
            images = [f for f in images if Util.is_image(f) and os.path.isfile(f)]
            self.add_sources(Options.SourceType.IMAGE, images)

        self.dialog = None
        chooser.destroy()

    def on_add_folders_clicked(self, widget=None):
        chooser = Gtk.FileChooserDialog(_("Add Folders - Only add the root folders, subfolders are searched recursively"),
            parent=self, action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=[_("Cancel"), Gtk.ResponseType.CANCEL, _("Add"), Gtk.ResponseType.OK])
        self.dialog = chooser
        chooser.set_select_multiple(True)
        chooser.set_local_only(True)
        response = chooser.run()

        if response == Gtk.ResponseType.OK:
            folders = list(chooser.get_filenames())
            folders = [f for f in folders if os.path.isdir(f)]
            self.add_sources(Options.SourceType.FOLDER, folders)

        self.dialog = None
        chooser.destroy()

    def add_sources(self, type, locations):
        self.ui.sources.get_selection().unselect_all()
        existing = {}
        for i, r in enumerate(self.ui.sources.get_model()):
            if r[1] == Options.type_to_str(type):
                if type == Options.SourceType.FOLDER:
                    existing[os.path.normpath(_u(r[2]))] = r, i
                else:
                    existing[self.model_row_to_source(r)[2]] = r, i

        newly_added = 0
        for f in locations:
            if type == Options.SourceType.FOLDER or type == Options.SourceType.IMAGE:
                f = os.path.normpath(f)
            elif type in UNREMOVEABLE_TYPES:
                f = list(existing.keys())[0] if existing else None  # reuse the already existing location, do not add another one

            if not f in existing:
                self.ui.sources.get_model().append(self.source_to_model_row([True, type, f]))
                self.ui.sources.get_selection().select_path(len(self.ui.sources.get_model()) - 1)
                self.ui.sources.scroll_to_cell(len(self.ui.sources.get_model()) - 1, None, False, 0, 0)
                newly_added += 1
            else:
                logger.info(lambda: "Source already exists, activating it: " + f)
                existing[f][0][0] = True
                self.ui.sources.get_selection().select_path(existing[f][1])
                self.ui.sources.scroll_to_cell(existing[f][1], None, False, 0, 0)

        return newly_added

    def focus_source_and_image(self, source, image):
        self.ui.notebook.set_current_page(0)
        self.ui.sources.get_selection().unselect_all()
        for i, r in enumerate(self.ui.sources.get_model()):
            if self.model_row_to_source(r)[1:] == source[1:]:
                self.focused_image = image
                self.ui.sources.get_selection().select_path(i)
                self.ui.sources.scroll_to_cell(i, None, False, 0, 0)
                return

    def remove_sources(self, widget=None, delete_files = False):
        model, rows = self.ui.sources.get_selection().get_selected_rows()

        if delete_files:
            for row in rows:
                type = Options.str_to_type(model[row][1])
                if type in Options.SourceType.dl_types and type not in UNREMOVEABLE_TYPES:
                    source = self.model_row_to_source(model[row])
                    self.parent.delete_files_of_source(source)

        # store the treeiters from paths
        iters = []
        for row in rows:
            if Options.str_to_type(model[row][1]) not in UNREMOVEABLE_TYPES:
                iters.append(model.get_iter(row))
        # remove the rows (treeiters)
        for i in iters:
            if i is not None:
                model.remove(i)

    def on_source_doubleclicked(self, tree_view, row_index, arg4=None):
        self.edit_source(self.ui.sources.get_model()[row_index])

    def on_edit_source_clicked(self, widget=None):
        model, rows = self.ui.sources.get_selection().get_selected_rows()
        if len(rows) == 1:
            self.edit_source(model[rows[0]])

    def on_use_clicked(self, widget=None):
        model, rows = self.ui.sources.get_selection().get_selected_rows()
        for row in model:
            row[0] = False
        for path in rows:
            model[path][0] = True
        for row in model:
            #TODO we trigger for all rows, though some of them don't actually change state - but no problem for now
            self.on_row_enabled_state_changed(row)
        self.on_sources_selection_changed()

    def edit_source(self, edited_row):
        type = Options.str_to_type(edited_row[1])

        if type == Options.SourceType.IMAGE or type == Options.SourceType.FOLDER:
            subprocess.call(["xdg-open", os.path.realpath(_u(edited_row[2]))])
        elif type == Options.SourceType.FAVORITES:
            subprocess.call(["xdg-open", self.parent.options.favorites_folder])
        elif type == Options.SourceType.FETCHED:
            subprocess.call(["xdg-open", self.parent.options.fetched_folder])
        elif type in EDITABLE_TYPES:
            if type == Options.SourceType.FLICKR:
                self.dialog = AddFlickrDialog()
            elif type == Options.SourceType.WALLHAVEN:
                self.dialog = AddWallhavenDialog()
            elif type == Options.SourceType.REDDIT:
                self.dialog = AddRedditDialog()
            elif type == Options.SourceType.MEDIA_RSS:
                self.dialog = AddMediaRssDialog()

            self.dialog.set_edited_row(edited_row)
            self.show_dialog(self.dialog)

    def on_sources_selection_changed(self, widget=None):
        model, rows = self.ui.sources.get_selection().get_selected_rows()

        enabled = set(i for i, row in enumerate(model) if row[0])
        selected = set(row.get_indices()[0] for row in rows)
        self.ui.use_button.set_sensitive(selected and enabled != selected)

        if hasattr(self, "previous_selection") and rows == self.previous_selection:
            return

        self.previous_selection = rows

        self.ui.edit_source.set_sensitive(False)
        self.ui.edit_source.set_label(_("Edit..."))

        if len(rows) == 1:
            source = model[rows[0]]
            type = Options.str_to_type(source[1])
            if type == Options.SourceType.IMAGE:
                self.ui.edit_source.set_sensitive(True)
                self.ui.edit_source.set_label(_("View Image"))
            elif type in [Options.SourceType.FOLDER, Options.SourceType.FAVORITES, Options.SourceType.FETCHED]:
                self.ui.edit_source.set_sensitive(True)
                self.ui.edit_source.set_label(_("Open Folder"))
            elif type in EDITABLE_TYPES:
                self.ui.edit_source.set_sensitive(True)
                self.ui.edit_source.set_label(_("Edit..."))

        def timer_func():
            self.show_thumbs(list(model[row] for row in rows))
        if hasattr(self, "show_timer") and self.show_timer:
            self.show_timer.cancel()
        self.show_timer = threading.Timer(0.3, timer_func)
        self.show_timer.start()

        for row in rows:
            if Options.str_to_type(model[row][1]) in UNREMOVEABLE_TYPES:
                self.ui.remove_sources.set_sensitive(False)
                return

        self.ui.remove_sources.set_sensitive(len(rows) > 0)

    def model_row_to_source(self, row):
        return [row[0],
                Options.str_to_type(row[1]),
                Texts.SOURCES[row[1]][0] if row[1] in Texts.SOURCES else _u(row[2])]

    def source_to_model_row(self, s):
        srctype = Options.type_to_str(s[1])
        return [s[0], srctype, s[2] if not srctype in Texts.SOURCES else Texts.SOURCES[srctype][1]]

    def show_thumbs(self, source_rows, pin=False, thumbs_type=None):
        try:
            if not source_rows:
                return

            self.parent.thumbs_manager.hide(gdk_thread=False, force=True)

            images = []
            folders = []
            image_count = 0

            for row in source_rows:
                if not row:
                    continue

                type = Options.str_to_type(row[1])
                if type == Options.SourceType.IMAGE:
                    image_count += 1
                    images.append(_u(row[2]))
                else:
                    folder = self.parent.get_folder_of_source(self.model_row_to_source(row))
                    image_count += sum(1 for f in Util.list_files(folders=(folder,), filter_func=Util.is_image, max_files=1, randomize=False))
                    folders.append(folder)

            if image_count > -1:
                folder_images = list(Util.list_files(folders=folders, filter_func=Util.is_image, max_files=1000))
                random.shuffle(folder_images)
                to_show = images + folder_images[:100]
                if hasattr(self, "focused_image") and self.focused_image is not None:
                    try:
                        to_show.remove(self.focused_image)
                    except Exception:
                        pass
                    to_show.insert(0, self.focused_image)
                    self.focused_image = None
                self.parent.thumbs_manager.show(
                    to_show, gdk_thread=False, screen=self.get_screen(), folders=folders, type=thumbs_type)
                if pin:
                    self.parent.thumbs_manager.pin()
                if thumbs_type:
                    self.parent.update_indicator(is_gtk_thread=False, auto_changed=False)

        except Exception:
            logger.exception(lambda: "Could not create thumbs window:")

    def on_add_mediarss_clicked(self, widget=None):
        self.show_dialog(AddMediaRssDialog())

    def on_add_reddit_clicked(self, widget=None):
        self.show_dialog(AddRedditDialog())

    def on_add_flickr_clicked(self, widget=None):
        self.show_dialog(AddFlickrDialog())

    def on_add_wallhaven_clicked(self, widget=None):
        self.show_dialog(AddWallhavenDialog())

    def show_dialog(self, dialog):
        self.dialog = dialog
        self.dialog.parent = self
        self.dialog.set_transient_for(self)
        response = self.dialog.run()
        if response != Gtk.ResponseType.OK:
            if self.dialog:
                self.dialog.destroy()
            self.dialog = None

    def on_add_dialog_okay(self, source_type, location, edited_row):
        if edited_row:
            edited_row[2] = location
        else:
            self.add_sources(source_type, [location])
        self.dialog = None

    def close(self):
        self.ui.error_downloaded.set_label("")
        self.ui.error_favorites.set_label("")
        self.ui.error_fetched.set_label("")

        self.hide()
        self.parent.trigger_download()
        self.on_destroy()

        self.parent.show_usage_stats_notice()

    def on_save_clicked(self, widget):
        self.delayed_apply()
        self.close()

    def delayed_apply(self, widget=None, *arg):
        if not self.loading:
            self.delayed_apply_with_interval(0.1)

    def delayed_apply_slow(self, widget=None, *arg):
        if not self.loading:
            self.delayed_apply_with_interval(1)

    def delayed_apply_with_interval(self, interval):
        if not self.loading:
            if hasattr(self, "apply_timer") and self.apply_timer:
                self.apply_timer.cancel()
                self.apply_timer = None

            self.apply_timer = threading.Timer(interval, self.apply)
            self.apply_timer.start()

    def apply(self):
        try:
            logger.info(lambda: "Applying preferences")

            self.options = Options()
            self.options.read()

            self.options.change_enabled = self.ui.change_enabled.get_active()
            self.options.change_on_start = self.ui.change_on_start.get_active()
            self.options.change_interval = self.get_change_interval()
            self.options.safe_mode = self.ui.safe_mode.get_active()

            self.options.download_enabled = self.ui.download_enabled.get_active()
            self.options.download_interval = self.get_download_interval()

            self.options.quota_enabled = self.ui.quota_enabled.get_active()
            try:
                self.options.quota_size = int(self.ui.quota_size.get_text())
                if self.options.quota_size < 50:
                    self.options.quota_size = 50
            except Exception:
                logger.exception(lambda: "Could not understand quota size")

            if os.access(self.dl_chooser.get_folder(), os.W_OK):
                self.options.download_folder = self.dl_chooser.get_folder()
            if os.access(self.fav_chooser.get_folder(), os.W_OK):
                self.options.favorites_folder = self.fav_chooser.get_folder()
            self.options.favorites_operations = self.favorites_operations

            self.options.sources = []
            for r in self.ui.sources.get_model():
                self.options.sources.append(self.model_row_to_source(r))

            if os.access(self.fetched_chooser.get_folder(), os.W_OK):
                self.options.fetched_folder = self.fetched_chooser.get_folder()
            self.options.clipboard_enabled = self.ui.clipboard_enabled.get_active()
            self.options.clipboard_use_whitelist = self.ui.clipboard_use_whitelist.get_active()
            buf = self.ui.clipboard_hosts.get_buffer()
            self.options.clipboard_hosts = Util.split(_u(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)))

            if self.ui.icon.get_active() == 0:
                self.options.icon = "Light"
            elif self.ui.icon.get_active() == 1:
                self.options.icon = "Dark"
            elif self.ui.icon.get_active() == 2:
                self.options.icon = "Current"
            elif self.ui.icon.get_active() == 4:
                self.options.icon = "None"
            elif self.ui.icon.get_active() == 3:
                file = _u(self.ui.icon_chooser.get_filename())
                if file and os.access(file, os.R_OK):
                    self.options.icon = file
                else:
                    self.options.icon = "Light"

            if self.ui.favorites_operations.get_active() == 0:
                self.options.favorites_operations = [["/", "Copy"]]
            elif self.ui.favorites_operations.get_active() == 1:
                self.options.favorites_operations = [["/", "Move"]]
            elif self.ui.favorites_operations.get_active() == 2:
                self.options.favorites_operations = [["/", "Both"]]
            elif self.ui.favorites_operations.get_active() == 3:
                # will be set in the favops editor dialog
                pass

            self.options.smart_enabled = self.ui.smart_enabled.get_active()
            if self.ui.sync_enabled.get_sensitive():
                self.options.sync_enabled = self.ui.sync_enabled.get_active()
            self.options.stats_enabled = self.ui.stats_enabled.get_active()

            self.options.facebook_show_dialog = self.ui.facebook_show_dialog.get_active()

            self.options.copyto_enabled = self.ui.copyto_enabled.get_active()
            copyto = os.path.normpath(self.copyto_chooser.get_folder())
            if copyto == os.path.normpath(self.parent.get_actual_copyto_folder('Default')):
                self.options.copyto_folder = 'Default'
            else:
                self.options.copyto_folder = copyto

            self.options.desired_color_enabled = self.ui.desired_color_enabled.get_active()
            c = self.ui.desired_color.get_color()
            self.options.desired_color = (c.red // 256, c.green // 256, c.blue // 256)

            self.options.min_size_enabled = self.ui.min_size_enabled.get_active()
            try:
                self.options.min_size = int(self.ui.min_size.get_active_text())
            except Exception:
                pass

            self.options.use_landscape_enabled = self.ui.landscape_enabled.get_active()

            self.options.lightness_enabled = self.ui.lightness_enabled.get_active()
            self.options.lightness_mode = \
                Options.LightnessMode.DARK if self.ui.lightness.get_active() == 0 else Options.LightnessMode.LIGHT

            self.options.min_rating_enabled = self.ui.min_rating_enabled.get_active()
            try:
                self.options.min_rating = int(self.ui.min_rating.get_active_text())
            except Exception:
                pass

            self.options.clock_enabled = self.ui.clock_enabled.get_active()
            self.options.clock_font = _u(self.ui.clock_font.get_font_name())
            self.options.clock_date_font = _u(self.ui.clock_date_font.get_font_name())

            self.options.quotes_enabled = self.ui.quotes_enabled.get_active()
            self.options.quotes_font = _u(self.ui.quotes_font.get_font_name())
            c = self.ui.quotes_text_color.get_color()
            self.options.quotes_text_color = (c.red // 256, c.green // 256, c.blue // 256)
            c = self.ui.quotes_bg_color.get_color()
            self.options.quotes_bg_color = (c.red // 256, c.green // 256, c.blue // 256)
            self.options.quotes_bg_opacity = max(0, min(100, int(self.ui.quotes_bg_opacity.get_value())))
            self.options.quotes_text_shadow = self.ui.quotes_text_shadow.get_active()
            self.options.quotes_tags = _u(self.ui.quotes_tags.get_text())
            self.options.quotes_authors = _u(self.ui.quotes_authors.get_text())
            self.options.quotes_change_enabled = self.ui.quotes_change_enabled.get_active()
            self.options.quotes_change_interval = self.get_quotes_change_interval()
            self.options.quotes_width = max(0, min(100, int(self.ui.quotes_width.get_value())))
            self.options.quotes_hpos = max(0, min(100, int(self.ui.quotes_hpos.get_value())))
            self.options.quotes_vpos = max(0, min(100, int(self.ui.quotes_vpos.get_value())))

            self.options.quotes_disabled_sources = [
                cb.get_label() for cb in self.quotes_sources_checkboxes if not cb.get_active()]

            for f in self.options.filters:
                f[0] = self.filter_name_to_checkbox[f[1]].get_active()

            self.options.slideshow_sources_enabled = self.ui.slideshow_sources_enabled.get_active()
            self.options.slideshow_favorites_enabled = self.ui.slideshow_favorites_enabled.get_active()
            self.options.slideshow_downloads_enabled = self.ui.slideshow_downloads_enabled.get_active()
            self.options.slideshow_custom_enabled = self.ui.slideshow_custom_enabled.get_active()
            if os.access(self.slideshow_custom_chooser.get_folder(), os.R_OK):
                self.options.slideshow_custom_folder = self.slideshow_custom_chooser.get_folder()

            if self.ui.slideshow_sort_order.get_active() == 0:
                self.options.slideshow_sort_order = "Random"
            elif self.ui.slideshow_sort_order.get_active() == 1:
                self.options.slideshow_sort_order = "Name, asc"
            elif self.ui.slideshow_sort_order.get_active() == 2:
                self.options.slideshow_sort_order = "Name, desc"
            elif self.ui.slideshow_sort_order.get_active() == 3:
                self.options.slideshow_sort_order = "Date, asc"
            elif self.ui.slideshow_sort_order.get_active() == 4:
                self.options.slideshow_sort_order = "Date, desc"

            if self.ui.slideshow_monitor.get_active() == 0:
                self.options.slideshow_monitor = "All"
            else:
                self.options.slideshow_monitor = self.ui.slideshow_monitor.get_active()

            if self.ui.slideshow_mode.get_active() == 0:
                self.options.slideshow_mode = "Fullscreen"
            elif self.ui.slideshow_mode.get_active() == 1:
                self.options.slideshow_mode = "Desktop"
            elif self.ui.slideshow_mode.get_active() == 2:
                self.options.slideshow_mode = "Maximized"
            elif self.ui.slideshow_mode.get_active() == 3:
                self.options.slideshow_mode = "Window"

            self.options.slideshow_seconds = max(0.5, float(self.ui.slideshow_seconds.get_value()))
            self.options.slideshow_fade = max(0, min(1, float(self.ui.slideshow_fade.get_value())))
            self.options.slideshow_zoom = max(0, min(1, float(self.ui.slideshow_zoom.get_value())))
            self.options.slideshow_pan = max(0, min(0.2, float(self.ui.slideshow_pan.get_value())))

            self.options.write()

            if not self.parent.running:
                return

            self.parent.reload_config()

            self.update_autostart()
        except Exception:
            if self.parent.running:
                logger.exception(lambda: "Error while applying preferences")
                dialog = Gtk.MessageDialog(self, Gtk.DialogFlags.MODAL,
                    Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                    "An error occurred while saving preferences.\n"
                    "Please run from a terminal with the -v flag and try again.")
                dialog.set_title("Oops")
                dialog.run()
                dialog.destroy()

    def update_autostart(self):
        file = os.path.expanduser(u"~/.config/autostart/variety.desktop")

        if not self.ui.autostart.get_active():
            try:
                if os.path.exists(file):
                    logger.info(lambda: "Removing autostart entry")
                    os.unlink(file)
            except Exception:
                logger.exception(lambda: "Could not remove autostart entry variety.desktop")
        else:
            if not os.path.exists(file):
                self.parent.create_autostart_entry()


    def on_change_enabled_toggled(self, widget = None):
        self.ui.change_interval_text.set_sensitive(self.ui.change_enabled.get_active())
        self.ui.change_interval_time_unit.set_sensitive(self.ui.change_enabled.get_active())

    def on_quotes_change_enabled_toggled(self, widget = None):
        self.ui.quotes_change_interval_text.set_sensitive(self.ui.quotes_change_enabled.get_active())
        self.ui.quotes_change_interval_time_unit.set_sensitive(self.ui.quotes_change_enabled.get_active())

    def on_download_enabled_toggled(self, widget = None):
        active = self.ui.download_enabled.get_active()
        self.ui.download_interval_text.set_sensitive(active)
        self.ui.download_interval_time_unit.set_sensitive(active)
        self.ui.download_folder_chooser.set_sensitive(active)
        self.ui.quota_enabled.set_sensitive(active)
        self.ui.quota_size.set_sensitive(active)
        self.on_quota_enabled_toggled()

    def on_quota_enabled_toggled(self, widget = None):
        active = self.ui.download_enabled.get_active() and self.ui.quota_enabled.get_active()
        self.ui.quota_size.set_sensitive(active)

    def on_desired_color_enabled_toggled(self, widget = None):
        self.ui.desired_color.set_sensitive(self.ui.desired_color_enabled.get_active())

    def on_min_size_enabled_toggled(self, widget = None):
        self.ui.min_size.set_sensitive(self.ui.min_size_enabled.get_active())
        self.ui.min_size_label.set_sensitive(self.ui.min_size_enabled.get_active())

    def on_min_rating_enabled_toggled(self, widget = None):
        self.ui.min_rating.set_sensitive(self.ui.min_rating_enabled.get_active())

    def on_lightness_enabled_toggled(self, widget = None):
        self.ui.lightness.set_sensitive(self.ui.lightness_enabled.get_active())

    def on_smart_enabled_toggled(self, widget=None):
        self.on_smart_user_updated()
        if not self.ui.smart_enabled.get_active():
            for s in self.parent.options.sources:
                if s[1] in (Options.SourceType.RECOMMENDED,) and s[0]:
                    self.parent.show_notification(_("Recommended images source disabled"))
                    s[0] = False
                    self.parent.options.write()
            for i, r in enumerate(self.ui.sources.get_model()):
                if Options.str_to_type(r[1]) in (Options.SourceType.RECOMMENDED,):
                    r[0] = False
        elif not self.parent.smart.user:
            def _f():
                self.parent.smart.load_user(create_if_missing=True)
            threading.Timer(0, _f).start()

    def on_destroy(self, widget = None):
        if hasattr(self, "dialog") and self.dialog:
            try:
                self.dialog.destroy()
            except Exception:
                pass
        for chooser in (self.dl_chooser, self.fav_chooser, self.fetched_chooser):
            try:
                chooser.destroy()
            except Exception:
                pass
        self.parent.thumbs_manager.hide(gdk_thread=True, force=False)

    def on_downloaded_changed(self, widget=None):
        self.delayed_apply()

        if not os.access(self.dl_chooser.get_folder(), os.W_OK):
            self.ui.error_downloaded.set_label(_("No write permissions"))
        else:
            self.ui.error_downloaded.set_label("")

        if not self.loading and self.ui.quota_enabled.get_active():
            self.ui.quota_enabled.set_active(False)
            self.parent.show_notification(
                _("Limit disabled"),
                _("Changing the download folder automatically turns off the size limit to prevent from accidental data loss"),
                important=True)

    def update_real_download_folder(self):
        if not Util.same_file_paths(self.parent.options.download_folder, self.parent.real_download_folder):
            self.ui.real_download_folder.set_visible(True)
        self.ui.real_download_folder.set_text(_("Actual download folder: %s ") % self.parent.real_download_folder)

    def on_favorites_changed(self, widget=None):
        self.delayed_apply()
        if not os.access(self.fav_chooser.get_folder(), os.W_OK):
            self.ui.error_favorites.set_label(_("No write permissions"))
        else:
            self.ui.error_favorites.set_label("")


    def on_fetched_changed(self, widget=None):
        self.delayed_apply()
        if not os.access(self.fetched_chooser.get_folder(), os.W_OK):
            self.ui.error_fetched.set_label(_("No write permissions"))
        else:
            self.ui.error_fetched.set_label("")

    def update_clipboard_state(self, widget=None):
        self.ui.clipboard_use_whitelist.set_sensitive(self.ui.clipboard_enabled.get_active())
        # keep the hosts list always enabled - user can wish to add hosts even when monitoring is not enabled - if undesired, uncomment below:
        # self.ui.clipboard_hosts.set_sensitive(self.ui.clipboard_enabled.get_active() and self.ui.clipboard_use_whitelist.get_active())

    def on_edit_favorites_operations_clicked(self, widget=None):
        self.dialog = EditFavoriteOperationsDialog()
        self.dialog.set_transient_for(self)
        buf = self.dialog.ui.textbuffer
        buf.set_text('\n'.join(':'.join(x) for x in self.favorites_operations))
        if self.dialog.run() == Gtk.ResponseType.OK:
            text = _u(buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False))
            self.favorites_operations = list([x.strip().split(':') for x in text.split('\n') if x])
            self.delayed_apply()
        self.dialog.destroy()
        self.dialog = None

    def on_icon_changed(self, widget=None):
        self.ui.icon_chooser.set_visible(self.ui.icon.get_active() == 3)

    def on_favorites_operations_changed(self, widget=None):
        self.ui.edit_favorites_operations.set_visible(self.ui.favorites_operations.get_active() == 3)

    def on_copyto_enabled_toggled(self, widget=None):
        self.copyto_chooser.set_sensitive(self.ui.copyto_enabled.get_active())
        self.ui.copyto_use_default.set_sensitive(self.ui.copyto_enabled.get_active())
        self.on_copyto_changed()

    def on_copyto_changed(self):
        self.ui.copyto_faq_link.set_sensitive(self.ui.copyto_enabled.get_active())
        if self.ui.copyto_enabled.get_active() and self.copyto_chooser.get_folder():
            folder = self.copyto_chooser.get_folder()
            self.ui.copyto_use_default.set_sensitive(folder != self.parent.get_actual_copyto_folder('Default'))
            under_encrypted = Util.is_home_encrypted() and folder.startswith(os.path.expanduser('~') + '/')
            self.ui.copyto_encrypted_note.set_visible(under_encrypted)
            can_write = os.access(self.parent.get_actual_copyto_folder(folder), os.W_OK)
            can_read = os.stat(folder).st_mode | stat.S_IROTH
            self.ui.copyto_faq_link.set_visible(can_write and can_read and not under_encrypted)
            self.ui.copyto_permissions_box.set_visible(not can_write or not can_read)
            self.ui.copyto_write_permissions_warning.set_visible(not can_write)
            self.ui.copyto_read_permissions_warning.set_visible(not can_read)
        else:
            self.ui.copyto_faq_link.set_visible(True)
            self.ui.copyto_encrypted_note.set_visible(False)
            self.ui.copyto_permissions_box.set_visible(False)
        self.delayed_apply()

    def on_copyto_use_default_clicked(self, widget=None):
        self.copyto_chooser.set_folder(self.parent.get_actual_copyto_folder('Default'))
        self.on_copyto_changed()

    def on_copyto_fix_permissions_clicked(self, widget=None):
        folder = self.copyto_chooser.get_folder()
        can_write = os.access(self.parent.get_actual_copyto_folder(folder), os.W_OK)
        can_read = os.stat(folder).st_mode | stat.S_IROTH
        mode = 'a+'
        if not can_read: mode += 'r'
        if not can_write: mode += 'w'
        try:
            Util.superuser_exec("chmod", mode, folder)
        except Exception:
            logger.exception(lambda: "Could not adjust copyto folder permissions")
            self.parent.show_notification(
                _("Could not adjust permissions"),
                _('You may try manually running this command:\nsudo chmod %s "%s"') % (mode, folder))
        self.on_copyto_changed()

    def on_btn_login_register_clicked(self, widget=None):
        if hasattr(self, 'dialog') and self.dialog and isinstance(self.dialog, LoginOrRegisterDialog):
            return
        login_dialog = LoginOrRegisterDialog()
        login_dialog.set_smart(self.parent.smart)
        self.show_dialog(login_dialog)

    def close_login_register_dialog(self):
        if hasattr(self, "dialog") and self.dialog and isinstance(self.dialog, LoginOrRegisterDialog):
            def _close():
                self.dialog.destroy()
                self.dialog = None
            GObject.idle_add(_close)

    def on_smart_user_updated(self, create_user_attempts=0):
        self.update_status_message()

        sync_allowed = self.ui.smart_enabled.get_active() and self.parent.smart.is_registered()
        self.ui.sync_enabled.set_sensitive(sync_allowed)
        self.ui.sync_login_note.set_visible(not sync_allowed)
        if not sync_allowed:
            self.ui.sync_enabled.set_active(False)
        else:
            self.ui.sync_enabled.set_active(self.options.sync_enabled)

        if self.parent.smart.user:
            self.ui.box_smart_connecting.set_visible(False)
            self.ui.box_smart_user.set_visible(True)
            username = self.parent.smart.user.get("username")
            self.ui.smart_username.set_markup(_('Logged in as: ') + '<a href="%s">%s</a>' % (
                    self.parent.smart.get_profile_url(),
                    username or _('Anonymous')))
            self.ui.btn_login_register.set_label(_('Login or register') if not bool(username) else _('Switch user'))
            self.ui.smart_register_note.set_visible(not bool(username))
        else:
            if not self.ui.smart_enabled.get_active():
                self.ui.box_smart_connecting.set_visible(False)
                self.ui.box_smart_user.set_visible(False)
            elif create_user_attempts == 0:
                def _create_user():
                    def _start():
                        self.ui.smart_spinner.set_visible(True)
                        self.ui.smart_spinner.start()
                        self.ui.smart_connect_error.set_visible(False)
                        self.ui.box_smart_connecting.set_visible(True)
                    GObject.idle_add(_start)

                    try:
                        self.parent.smart.load_user(create_if_missing=True)
                        self.on_smart_user_updated(create_user_attempts + 1)
                    except IOError:
                        def _fail():
                            self.ui.smart_spinner.set_visible(False)
                            self.ui.smart_connect_error.set_visible(True)
                        GObject.idle_add(_fail)
                    finally:
                        def _stop():
                            self.ui.smart_spinner.set_visible(False)
                        GObject.idle_add(_stop)
                threading.Timer(0, _create_user).start()

    def on_btn_slideshow_reset_clicked(self, widget=None):
        self.ui.slideshow_seconds.set_value(6)
        self.ui.slideshow_fade.set_value(0.4)
        self.ui.slideshow_zoom.set_value(0.2)
        self.ui.slideshow_pan.set_value(0.05)

    def on_btn_slideshow_start_clicked(self, widget=None):
        self.apply()
        self.parent.on_start_slideshow()