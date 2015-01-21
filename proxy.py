#!/usr/bin/env python
# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4
#
# Copyright (C) 2009-2010 Fluendo, S.L. (www.fluendo.com).
# Copyright (C) 2009-2010 Marc-Andre Lureau <marcandre.lureau@gmail.com>
# Copyright (C) 2010 Zaheer Abbas Merali  <zaheerabbas at merali dot org>
# Copyright (C) 2010 Andoni Morales Alastruey <ylatuya@gmail.com>
# Copyright (C) 2014 Juan Font Alonso <juanfontalonso@gmail.com>

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE" in the source distribution for more information.

import sys
import os
import argparse

from twisted.web import server, resource
from twisted.web.server import NOT_DONE_YET
from twisted.internet import reactor


from fetcher import HLSFetcher
from m3u8 import M3U8

from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from SocketServer import ThreadingMixIn
import threading
from functools import partial
import urlparse


if sys.version_info < (2, 4):
    raise ImportError("Cannot run with Python version < 2.4")


class HLSControler:

    def __init__(self, fetcher=None):
        self.fetcher = fetcher
        self.player = None

        self._player_sequence = None
        self._n_segments_keep = None

    def set_player(self, player):
        self.player = player
        if player:
            self.player.connect_about_to_finish(self.on_player_about_to_finish)
            self._n_segments_keep = self.fetcher.n_segments_keep
            self.fetcher.n_segments_keep = -1

    def _start(self, first_file):
        (path, l, f) = first_file
        self._player_sequence = f['sequence']
        if self.player:
            self.player.set_uri(path)
            self.player.play()

    def start(self):
        d = self.fetcher.start()
        d.addCallback(self._start)

    def _set_next_uri(self):
        # keep only the past three segments
        if self._n_segments_keep != -1:
            self.fetcher.delete_cache(lambda x:
                x <= self._player_sequence - self._n_segments_keep)
        self._player_sequence += 1
        d = self.fetcher.get_file(self._player_sequence)
        d.addCallback(self.player.set_uri)

    def on_player_about_to_finish(self):
        if not self.player._request._disconnected:
            reactor.callFromThread(self._set_next_uri)
        else:
            self.fetcher.stop()
            self._start = None
            del self.fetcher
            del self.player
            

class HTTPPlayer:
    def __init__(self, request):
        print "Starting player"
        self._playing = False
        self._need_data = False
        self._cb = None
        self._request = request

    def need_data(self):
        print "need"
        return self._need_data

    def play(self):
        self._playing = True

    def stop(self):
        print "stop"
        self._playing = False

    def set_uri(self, filepath):
        size = os.path.getsize(filepath)
        print str(size)
        count = 0            
        self._on_about_to_finish()
        
        with open(filepath, 'rb') as f:
            for chunk in iter(partial(f.read, 1024), ''):
              if not self._request._disconnected:
                  self._request.write(str(chunk))
                  count += 1024 
              else:
                  self.stop()
                  
                  break
        os.remove(filepath)         

    def on_message(self, bus, message):
        print "msg"
      
    def on_sync_message(self, bus, message):
        print "sync"

    def on_decoded_pad(self, decodebin, pad, more_pad):
        print "decoded"

    def on_enough_data(self):
        print("Player is full up!");
        self._need_data = False;
        
    def on_need_data(self, src, length):
        self._need_data = True;
        self._on_about_to_finish()

    def _on_about_to_finish(self, p=None):
        if self._cb:
            self._cb()

    def connect_about_to_finish(self, cb):
        self._cb = cb


      
def quit_server(): #workaround
    os.system("kill -9 "+str(os.getpid()))


class HLSProxy(resource.Resource):
    isLeaf = True
    
    def render_GET(self, request):
        if 'url' in request.args:
          url = request.args['url'][0]
          c = HLSControler(HLSFetcher(url))
          p = HTTPPlayer(request)
          c.set_player(p)
          c.start()
          return NOT_DONE_YET
          
          
        

class ThreadedHTTPServer(HTTPServer, ThreadingMixIn):
    """Handle requests in a separate thread."""

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, dest="port", required=False, 
                        metavar="PORT", default=8081, help="Port")
    args = parser.parse_args()
    
    #server = ThreadedHTTPServer(('', args.port), Handler)
    

    print 'Starting server on port '+str(args.port)+', use <Ctrl-C> to stop'
    site = server.Site(HLSProxy())
    reactor.listenTCP(args.port, site)
    reactor.run()
    