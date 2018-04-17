import logging
import math
import cairo


class AudioLevelDisplay(object):
    """Displays a Level-Meter of another VideoDisplay into a GtkWidget"""

    def __init__(self, drawing_area):
        self.log = logging.getLogger(
            'AudioLevelDisplay[{}]'.format(drawing_area.get_name())
        )

        self.drawing_area = drawing_area

        self.levelrms = []
        self.levelpeak = []
        self.leveldecay = []

        # register on_draw handler
        self.drawing_area.connect('draw', self.on_draw)

    def on_draw(self, widget, cr):
        # number of audio-channels
        channels = len(self.levelrms)

        if channels == 0:
            return False

        width = self.drawing_area.get_allocated_width()
        height = self.drawing_area.get_allocated_height()

        # space between the channels in px
        margin = 2

        # 1 channel -> 0 margins, 2 channels -> 1 margin, 3 channels…
        channel_width = int((width - (margin * (channels - 1))) / channels)

        # self.log.debug(
        #     'width: %upx filled with %u channels of each %upx '
        #     'and %ux margin of %upx',
        #     width, channels, channel_width, channels - 1, margin
        # )

        # normalize db-value to 0…1 and multiply with the height
        rms_px = [self.normalize_db(db) * height for db in self.levelrms]
        peak_px = [self.normalize_db(db) * height for db in self.levelpeak]
        decay_px = [self.normalize_db(db) * height for db in self.leveldecay]

        # setup brightness levels for the different levels
        bg_fade = 0.25
        rms_fade = 1.0
        peak_fade = 0.75
        decay_invers_fade = 0.5

        # setup gradients for all level bars
        bg_lg = cairo.LinearGradient(0, 0, 0, height)
        bg_lg.add_color_stop_rgb(0.0, bg_fade, 0, 0)
        bg_lg.add_color_stop_rgb(0.5, bg_fade, bg_fade, 0)
        bg_lg.add_color_stop_rgb(1.0, 0, bg_fade, 0)

        rms_lg = cairo.LinearGradient(0, 0, 0, height)
        rms_lg.add_color_stop_rgb(0.0, rms_fade, 0, 0)
        rms_lg.add_color_stop_rgb(0.5, rms_fade, rms_fade, 0)
        rms_lg.add_color_stop_rgb(1.0, 0, rms_fade, 0)

        peak_lg = cairo.LinearGradient(0, 0, 0, height)
        peak_lg.add_color_stop_rgb(0.0, peak_fade, 0, 0)
        peak_lg.add_color_stop_rgb(0.5, peak_fade, peak_fade, 0)
        peak_lg.add_color_stop_rgb(1.0, 0, peak_fade, 0)

        decay_lg = cairo.LinearGradient(0, 0, 0, height)
        decay_lg.add_color_stop_rgb(
            0.0, 1, decay_invers_fade, decay_invers_fade)
        decay_lg.add_color_stop_rgb(0.5, 1, 1, decay_invers_fade)
        decay_lg.add_color_stop_rgb(
            1.0, decay_invers_fade, 1, decay_invers_fade)

        # draw all level bars for all channels
        for channel in range(0, channels):
            # start-coordinate for this channel
            x = (channel * channel_width) + (channel * margin)

            # draw background
            cr.rectangle(x, 0, channel_width, height - peak_px[channel])
            cr.set_source(bg_lg)
            cr.fill()

            # draw peak bar
            cr.rectangle(
                x, height - peak_px[channel], channel_width, peak_px[channel])
            cr.set_source(peak_lg)
            cr.fill()

            # draw rms bar below
            cr.rectangle(
                x, height - rms_px[channel], channel_width,
                rms_px[channel] - peak_px[channel])
            cr.set_source(rms_lg)
            cr.fill()

            # draw decay bar
            cr.rectangle(x, height - decay_px[channel], channel_width, 2)
            cr.set_source(decay_lg)
            cr.fill()

        # draw db text-markers
        cr.set_source_rgb(1, 1, 1)
        for db in [-40, -20, -10, -5, -4, -3, -2, -1]:
            text = str(db)
            (xbearing, ybearing,
             textwidth, textheight,
             xadvance, yadvance) = cr.text_extents(text)

            y = self.normalize_db(db) * height
            cr.move_to((width - textwidth) / 2, height - y - textheight)
            cr.show_text(text)

        return True

    def normalize_db(self, db):
        # -60db -> 1.00 (very quiet)
        # -30db -> 0.75
        # -15db -> 0.50
        #  -5db -> 0.25
        #  -0db -> 0.00 (very loud)
        logscale = 1 - math.log10(-0.15 * db + 1)
        return self.clamp(logscale)

    def clamp(self, value, min_value=0, max_value=1):
        return max(min(value, max_value), min_value)

    def level_callback(self, rms, peak, decay):
        self.levelrms = rms
        self.levelpeak = peak
        self.leveldecay = decay
        self.drawing_area.queue_draw()
