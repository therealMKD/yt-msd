# Open Source Software under the Apache License, Version 2.0
# Part of the yt-msd GUI package (yt_msd.ui.stylesheet).
#
# A mixin, not a standalone module: MainApp inherits from this class, so what is written here
# are ordinary methods and `self` is the MainApp instance. They were lifted out of the class
# body in wave 6 with their text unchanged - only the imports needed to reach the rest of the
# program were added, and the inside of a multi-line string kept the indentation it was written
# with, because changing it would change what the program shows rather than where it is kept.

import os
import tempfile
from yt_msd.ui.theme import get_accent_color, get_system_appearance_mode
from yt_msd.ui.widgets import THUMB_BOX_PAUSED, THUMB_BOX_PLAYING

class StylesheetMixin:
    def apply_theme(self):
        mode = self.appearance_mode
        if mode == "System": mode = get_system_appearance_mode()
        
        accent = get_accent_color(self.accent_color_name)
        
        r = int(accent[1:3], 16)
        g = int(accent[3:5], 16)
        b = int(accent[5:7], 16)
        brightness = (r * 299 + g * 587 + b * 114) / 1000
        accent_fg = "#000000" if brightness > 150 else "#ffffff"
        
        # Write checkmark SVG to a temp file
        checkmark_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{accent_fg}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
        if not hasattr(self, '_checkmark_svg_path') or not os.path.exists(self._checkmark_svg_path):
            tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w', encoding='utf-8')
            tmp.write(checkmark_svg)
            tmp.close()
            self._checkmark_svg_path = tmp.name.replace('\\', '/')
        else:
            with open(self._checkmark_svg_path, 'w', encoding='utf-8') as f:
                f.write(checkmark_svg)
        checkmark_path = self._checkmark_svg_path
        
        # Write downarrow SVG to a temp file
        downarrow_svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{accent_fg}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>'
        if not hasattr(self, '_downarrow_svg_path') or not os.path.exists(self._downarrow_svg_path):
            tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w', encoding='utf-8')
            tmp.write(downarrow_svg)
            tmp.close()
            self._downarrow_svg_path = tmp.name.replace('\\', '/')
        else:
            with open(self._downarrow_svg_path, 'w', encoding='utf-8') as f:
                f.write(downarrow_svg)
        downarrow_path = self._downarrow_svg_path
        
        if mode == "Light":
            bg = "#f3f3f3"
            fg = "#1a1a1a"
            frame_bg = "#ffffff"
            input_bg = "#e8e8e8"
            input_border = "#ccc"
            scroll_bg = "#ffffff"
            splitter_handle = "#ddd"
            slider_bg = "#ddd"
            hover_bg = "#000000"
            hover_fg = "#ffffff"
            queue_item_bg = "#e8e8e8"
            queue_item_bg_finished = "#ffffff"
            btn_hover = "rgba(0, 0, 0, 0.1)"
            if self.accent_color_name == "White" or accent.upper() == "#FFFFFF":
                main_btn_border = "1px solid #ccc"
            else:
                main_btn_border = "none"
        else:
            bg = "#1e1e1e"
            fg = "#ffffff"
            frame_bg = "#2a2a2a"
            input_bg = "#333333"
            input_border = "#555"
            scroll_bg = "#1a1a1a"
            splitter_handle = "#333333"
            slider_bg = "#333"
            hover_bg = "#dddddd"
            hover_fg = "#1a1a1a"
            queue_item_bg = "#333333"
            queue_item_bg_finished = "#1a1a1a"
            btn_hover = "rgba(255, 255, 255, 0.1)"
            main_btn_border = "none"

        secondary_fg = "#777777" if mode == "Light" else "#999999"

        # Canonical tooltip style. Applied to the whole application (see below) so
        # every window — the main window and all dialogs — shows identical tooltips
        # with the same font size and appearance as the playback controls.
        tooltip_css = (
            "QToolTip {"
            f" background-color: {frame_bg};"
            f" color: {fg};"
            f" border: 1px solid {input_border};"
            " padding: 2px 6px;"
            " border-radius: 4px;"
            " font-family: 'Segoe UI';"
            " font-size: 10px;"
            " font-weight: normal;"
            " show-delay: 4000ms;"
            " }"
        )

        full_css = """
            QMainWindow, QDialog {{ background-color: {bg}; }}
            QWidget {{ color: {fg}; font-family: 'Segoe UI'; font-size: 13px; }}
            QWidget#scrollContent, DraggableQueueWidget#scrollContent {{ background-color: {scroll_bg}; }}
            QWidget#queueItemPending {{ background-color: {queue_item_bg}; border-radius: 4px; margin-bottom: 2px; }}
            QWidget#queueItemFinished {{ background-color: {queue_item_bg_finished}; border-radius: 4px; margin-bottom: 2px; }}
            QLabel {{ color: {fg}; }}
            QLabel#durationLabel {{ color: {secondary_fg}; font-size: 11px; background: transparent; border: none; }}
            QLabel#channelLabel {{ color: {secondary_fg}; font-size: 11px; background: transparent; border: none; }}
            QPushButton {{ 
                background-color: {accent}; 
                color: {accent_fg}; border: {main_btn_border}; padding: 6px 12px; border-radius: 4px; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {hover_bg}; color: {hover_fg}; }}
            QPushButton:disabled {{ background-color: #555555; color: #888888; }}
            QLineEdit {{ 
                background-color: {input_bg}; color: {fg}; border: 1px solid {input_border}; padding: 6px; border-radius: 4px;
            }}
            QComboBox {{ 
                background-color: {input_bg}; color: {fg}; border: 1px solid {input_border}; padding: 6px; border-radius: 4px;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 24px;
                border-left: 1px solid {input_border};
                background-color: {accent};
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
            }}
            QComboBox::down-arrow {{
                image: url("{downarrow_path}");
                width: 16px; height: 16px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {input_bg};
                color: {fg};
                selection-background-color: {accent};
                selection-color: {accent_fg};
                border: 1px solid {input_border};
            }}
            QScrollArea {{ border: none; background-color: {scroll_bg}; border-radius: 6px;}}
            QFrame {{ background-color: {frame_bg}; border-radius: 6px; padding: 5px;}}
            QSplitter::handle {{ background-color: {splitter_handle}; width: 6px; margin: 0px 2px; }}
            QSlider::groove:horizontal {{ border: none; height: 4px; background: {slider_bg}; border-radius: 2px; }}
            QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 16px; height: 16px; margin-top: -6px; margin-bottom: -6px; border-radius: 8px; }}
            QSlider#volSlider[volume_state="normal"]::sub-page:horizontal {{ background: {accent}; }}
            QSlider#volSlider[volume_state="normal"]::handle:horizontal {{ background: {accent}; }}
            QSlider#volSlider[volume_state="orange"]::sub-page:horizontal {{ background: #FF8C00; }}
            QSlider#volSlider[volume_state="orange"]::handle:horizontal {{ background: #FF8C00; }}
            QSlider#volSlider[volume_state="red"]::sub-page:horizontal {{ background: #E31E24; }}
            QSlider#volSlider[volume_state="red"]::handle:horizontal {{ background: #E31E24; }}
            QSlider#volSlider::sub-page:horizontal {{ border-radius: 1px; }}
            /* The volume read-out is typed as well as dragged now, so it is a QLineEdit - and
               every QLineEdit in the app above it gets a background, a border and 6 px of padding,
               which around a number in the player bar is a box nobody asked for. This takes the
               chrome off and leaves the caption where it always sat. The colour MainApp writes onto
               it at 101 and at 116 is only a colour, so it rides on top of this line instead of
               replacing it. */
            QLineEdit#volPct {{ background: transparent; border: none; padding: 0px; }}
            
            QCheckBox {{ color: {fg}; spacing: 8px; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {accent}; border-radius: 3px; background: {frame_bg}; }}
            QCheckBox::indicator:checked {{ background: {accent}; image: url("{checkmark_path}"); }}
            
            QPushButton#transparentBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                border-radius: 0px;
                padding: 4px;
                text-align: left;
            }}
            QPushButton#transparentBtn:hover {{
                background-color: {btn_hover};
            }}
            QWidget#localRow {{
                background-color: transparent;
                border-radius: 4px;
            }}
            QWidget#localRow[selected="true"] {{
                background-color: {accent};
            }}
            /* The row that is the track the player is holding wears the colour of that
               state - green while it runs, orange while it is held - and it is written
               after the selection rule so that a row which is both selected and playing
               says the thing the listener is looking at the folder list to find out. */
            QWidget#localRow[play_state="playing"] {{
                background-color: {THUMB_BOX_PLAYING};
            }}
            QWidget#localRow[play_state="paused"] {{
                background-color: {THUMB_BOX_PAUSED};
            }}
            /* A green and an orange row both carry saturated colour behind the text, so
               the text on them is fixed rather than left to the theme's own foreground,
               which is chosen to sit on the dark panes and not on these. */
            QWidget#localRow[play_state="playing"] QPushButton#transparentBtn,
            QWidget#localRow[play_state="paused"] QPushButton#transparentBtn,
            QWidget#localRow[play_state="playing"] QLabel#durationLabel,
            QWidget#localRow[play_state="paused"] QLabel#durationLabel {{
                color: #1a1a1a;
                font-weight: bold;
            }}
            QPushButton#transparentBtn[selected="true"] {{
                background-color: transparent;
                color: {accent_fg};
            }}
            QPushButton#transparentBtn[selected="true"]:hover {{
                background-color: {btn_hover};
            }}
            QLabel#durationLabel[selected="true"] {{ color: {accent_fg}; }}
            /* The duration sits just off the right edge of a local row. Saying it once
               here instead of styling every row separately keeps the row build cheap,
               and it is scoped to the local pane, where that 6px gap was designed. */
            QWidget#localRow QLabel#durationLabel {{ padding-right: 6px; }}
            QMenu#localContextMenu {{
                background-color: {frame_bg};
                color: {fg};
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu#localContextMenu::item {{
                padding: 6px 28px 6px 12px;
                border-radius: 3px;
            }}
            QMenu#localContextMenu::item:selected {{
                background-color: {accent};
                color: {accent_fg};
            }}
            QMenu#localContextMenu::item:disabled {{ color: {secondary_fg}; }}
            QMenu#localContextMenu::separator {{
                height: 1px;
                background: {input_border};
                margin: 4px 6px;
            }}
            QPushButton#iconBtn {{
                background-color: transparent;
                color: {fg};
                font-weight: normal;
                padding: 0px;
            }}
            QPushButton#topIconBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 15px;
                font-weight: normal;
                border: 1px solid {input_border};
                border-radius: 4px;
                padding: 0px;
            }}
            QPushButton#topIconBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 20px;
                font-weight: normal;
                border-radius: 6px;
                padding: 0px;
            }}
            QPushButton#playerBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#playerBtn[active="true"] {{
                background-color: {accent};
                color: {accent_fg};
                font-weight: bold;
            }}
            QPushButton#playerBtn[active="true"]:hover {{
                background-color: {hover_bg};
                color: {hover_fg};
            }}
            QPushButton#playerPlayBtn {{
                background-color: transparent;
                color: {fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 30px;
                font-weight: normal;
                border-radius: 8px;
                padding: 0px;
            }}
            QPushButton#playerPlayBtn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#stopAfterBtn {{
                background-color: transparent;
                color: {secondary_fg};
                font-family: 'Segoe MDL2 Assets';
                font-size: 20px;
                font-weight: normal;
                border-radius: 6px;
                padding: 0px 0px 6px 0px;
            }}
            QPushButton#stopAfterBtn:hover {{
                background-color: {btn_hover};
                color: {fg};
            }}
            QPushButton#stopAfterBtn[stop_after_state="once"] {{
                background-color: {accent};
                color: {accent_fg};
                font-weight: bold;
            }}
            QPushButton#stopAfterBtn[stop_after_state="always"] {{
                background-color: #E31E24;
                color: white;
                font-weight: bold;
            }}
            {tooltip_css}
        """.format(
            bg=bg, fg=fg, frame_bg=frame_bg, input_bg=input_bg, input_border=input_border,
            scroll_bg=scroll_bg, splitter_handle=splitter_handle, slider_bg=slider_bg,
            hover_bg=hover_bg, hover_fg=hover_fg, accent=accent, accent_fg=accent_fg,
            queue_item_bg=queue_item_bg, queue_item_bg_finished=queue_item_bg_finished,
            btn_hover=btn_hover, checkmark_path=checkmark_path, downarrow_path=downarrow_path,
            main_btn_border=main_btn_border, secondary_fg=secondary_fg,
            # The colours a row wears when it is the track the player is holding, shared with
            # the thumbnail box of a search row so both panes say the same thing in the same
            # green and the same orange.
            THUMB_BOX_PLAYING=THUMB_BOX_PLAYING, THUMB_BOX_PAUSED=THUMB_BOX_PAUSED,
            tooltip_css=tooltip_css
        )
        # Apply the theme at the widget level (as in 2.3). A single
        # self.setStyleSheet re-polishes only this window's subtree; routing it
        # through QApplication.setStyleSheet instead re-polishes every widget in
        # every top-level window, which is what made theme switching laggy. The
        # tooltip rules are embedded in full_css above and propagate to child
        # dialogs through this stylesheet, so no app-level call is required.
        self.setStyleSheet(full_css)
        self.update_shuffle_btn_style()
        self._update_stop_after_ui()
