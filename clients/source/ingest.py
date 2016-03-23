#!/usr/bin/env python3

# ingest.py
# source client for Voctomix

import sys

import gi
import signal
import os
import socket

import argparse

gi.require_version('Gst', '1.0')
from gi.repository import Gst, GstNet, GObject

# init GObject & Co. before importing local classes
GObject.threads_init()
Gst.init([])

# this is kinda icky.
sys.path.insert(0, '../..' )

import voctogui.lib.connection as Connection
# import lib.clock as ClockManager


def mk_video_src(args, videocaps):
    # make video soure part of pipeline

    video_device = "device={}".format(args.video_dev) \
        if args.video_dev else ""

    monitor = """tee name=t ! queue !
                    videoconvert ! fpsdisplaysink sync=false 
                    t. ! queue !""" \
        if args.monitor else ""


    if args.video_source == 'dv':
        video_src = """
            dv1394src name=videosrc {video_device}!
		dvdemux name=demux !
		queue !
		dvdec !
                {monitor}
		deinterlace mode=1 !
		videoconvert !
                videorate !
                videoscale !
            """
    
    elif args.video_source == 'hdv':
        video_src = """
            hdv1394src do-timestamp=true name=videosrc {video_device} !
		tsdemux name=demux!
		queue !
		decodebin !
                {monitor}
		deinterlace mode=1 !
		videorate !
                videoscale !
		videoconvert !
            """

    elif args.video_source == 'hdmi2usb':
        video_src = """
            v4l2src device=%s name=videosrc !
                queue !
		image/jpeg,width=1280,height=720 !
                jpegdec !
                {monitor}
                videoconvert !
                videorate !
            """

    elif args.video_source == 'ximage':
        video_src = """
            ximagesrc name=videosrc !
                {monitor}
		videoconvert !
                videorate !
                videoscale !
            """

    elif args.video_source == 'blackmagichdmi':
        video_src = """
            decklinkvideosrc mode=17 connection=2 !
                {monitor}
		videoconvert !
                videorate !
                videoscale !
            """

    elif args.video_source == 'test':
        video_src = """
            videotestsrc name=videosrc 
                pattern=ball 
                foreground-color=0x00ff0000 background-color=0x00440000 !
                {monitor}
            """

    video_src = video_src.format(
                    video_device=video_device,
                    monitor=monitor)

    video_src += videocaps + "!\n"

    return video_src

def mk_audio_src(args, audiocaps):

    audio_device = "device={}".format(args.audio_dev) \
        if args.audio_dev else ""

    if args.audio_source in [ 'dv', 'hdv' ]:
        # this only works if video is from DV also.
        # or some gst source that gets demux ed
        audio_src = """
            demux. !
                audioconvert !
                """

    elif args.audio_source == 'pulse':
        audio_src = """
                pulsesrc {audio_device} name=audiosrc !
                """.format(audio_device=audio_device)

    elif args.audio_source == 'blackmagichdmi':
        audio_src = """
            decklinkaudiosrc !
            """

    elif args.audio_source == 'test':
        audio_src = """
            audiotestsrc name=audiosrc freq=330 !
            """
    audio_src += audiocaps + "!\n"

    return audio_src

def mk_mux(args):

    mux = """
     mux.
            matroskamux name=mux !
        """
    return mux

def mk_client(args):
    core_ip = socket.gethostbyname(args.host)
    client = """ 
                 tcpclientsink host={host} port={port}
                 """.format(host=core_ip, port=args.port)

    return client


def mk_pipeline(args, server_caps):

    video_src = mk_video_src(args, server_caps['videocaps'])
    audio_src = mk_audio_src(args, server_caps['audiocaps'])
    mux = mk_mux(args)
    client = mk_client(args)

    pipeline = video_src + "mux.\n" + audio_src + mux + client

    # remove blank lines to make it more human readable
    pipeline = pipeline.replace("\n\n","\n")

    return pipeline

def get_server_caps():


    # fetch config from server
    server_config = Connection.fetchServerConfig()
    server_caps = {'videocaps': server_config['mix']['videocaps'],
            'audiocaps': server_config['mix']['audiocaps']}

    return server_caps

    # obtain network-clock
    ClockManager.obtainClock(Connection.ip)


def run_pipeline(pipeline, args):

    core_ip = socket.gethostbyname(args.host)

    clock = GstNet.NetClientClock.new('voctocore', core_ip, 9998, 0)
    print('obtained NetClientClock from host', clock)

    print('waiting for NetClientClock to sync…')
    clock.wait_for_sync(Gst.CLOCK_TIME_NONE)

    print('starting pipeline')
    senderPipeline = Gst.parse_launch(pipeline)
    senderPipeline.use_clock(clock)
    src = senderPipeline.get_by_name('src')

    def on_eos(self, bus, message):
        print('Received EOS-Signal')
        sys.exit(1)

    def on_error(self, bus, message):
        print('Received Error-Signal')
        (error, debug) = message.parse_error()
        print('Error-Details: #%u: %s' % (error.code, debug))
        sys.exit(1)


    # Binding End-of-Stream-Signal on Source-Pipeline
    senderPipeline.bus.add_signal_watch()
    senderPipeline.bus.connect("message::eos", on_eos)
    senderPipeline.bus.connect("message::error", on_error)

    print("playing")
    senderPipeline.set_state(Gst.State.PLAYING)
 
    mainloop = GObject.MainLoop()
    try:
        mainloop.run()
    except KeyboardInterrupt:
        print('Terminated via Ctrl-C')




def get_args():

    parser = argparse.ArgumentParser(description='Vocto-ingest client')
    
    parser.add_argument('-v', '--verbose', action='count', default=0,
            help="Also print INFO and DEBUG messages.")

    parser.add_argument( '--video-source', action='store', 
            choices=[
                'dv', 'hdv', 'hdmi2usb', 'blackmagichdmi', 
                'ximage',
                'test', ], 
            default='test',
            help="Where to get video from")

    parser.add_argument( '--video-dev', action='store', 
            help="video device")

    parser.add_argument( '--audio-source', action='store', 
            choices=['dv', 'alsa', 'pulse', 'blackmagichdmi', 'test'], 
            default='test',
            help="Where to get audio from")

    parser.add_argument( '--audio-dev', action='store', 
            default='hw:CARD=CODEC',
            help="for alsa/pulse, audio device")
            # maybe hw:1,0

    parser.add_argument( '--audio-delay', action='store', 
            default='10',
            help="ms to delay audio")

    parser.add_argument('-m', '--monitor', action='store_true',
            help="fps display sink")

    parser.add_argument( '--host', action='store', 
            default='localhost',
            help="hostname of vocto core")

    parser.add_argument( '--port', action='store', 
            default='10000',
            help="port of vocto core")

    args = parser.parse_args()

    return args

    
def main():
    
    args = get_args()

    core_ip = socket.gethostbyname(args.host)
    # establish a synchronus connection to server
    Connection.establish(core_ip) 

    server_caps = get_server_caps()

    pipeline = mk_pipeline(args, server_caps)
    print(pipeline)
    run_pipeline(pipeline, args)



if __name__ == '__main__':
    main()
