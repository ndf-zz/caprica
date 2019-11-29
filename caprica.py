#!/usr/bin/python3
#
# Crude replacement for Galactica + DHI with built-in clock
#
# Imports
import argparse
import signal
import queue
import threading
import time
import socketserver
import socket
import cairo
import os
import sys
import math
from pkg_resources import resource_filename, resource_exists

# Configuration
VERSION = '1.0.0'
DEFPORT = 2004 - 58		# DHI port "58 years before the fall"
DEFFB = '@caprica-144x72'	# display socket address
WIDTH = 144			# display width
HEIGHT = 72			# display height
LINEH = 10			# pixel height of all text lines
HDRGAP = 4			# margin between header and result lines

# Program constants
GLW = 6				# glyph width
GLH = 8				# glyph height
GLPW = 32			# number of glyphs per row in source map
GLSZ = 0x100			# number of glyphs in source map
FBFONT = 'unifont'		# fallback for undefined glyphs
TIMEOUT = 30			# revert to clock after timeout seconds
CKH = 71			# height of clock
CKFONT = 'NotoSans'		# font style for clock info text
CKFH = 13.0			# height of clock info text
DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

# Image resource files
GLSRC = resource_filename(__name__, 'data/ISO-8859-1.png')
CKOPEN = resource_filename(__name__, 'data/clockpip-open.png')
CKCLOSE = resource_filename(__name__, 'data/clockpip-close.png')
CKOPEN = resource_filename(__name__, 'data/clockpip-open.png')
CKCLOSE = resource_filename(__name__, 'data/clockpip-close.png')
CKFACE = resource_filename(__name__, 'data/clockface-71.png')

# UNT4 message wrapper (based on metarace unt4 lib)
class unt4(object):
    # UNT4 mode 1 constants (mostly ascii)
    NUL = 0x00
    SOH = 0x01
    STX = 0x02
    ETX = 0x03
    EOT = 0x04
    ACK = 0x06
    BEL = 0x07
    HOME= 0x08
    CR  = 0x0d
    LF  = 0x0a
    ERL = 0x0b
    ERP = 0x0c
    DLE = 0x10
    DC2 = 0x12
    DC3 = 0x13
    DC4 = 0x14
    SYN = 0x16
    ETB = 0x17
    FS = 0x1c
    GS = 0x1d
    RS = 0x1e
    US = 0x1f
    tmap = str.maketrans({SOH:0x20,STX:0x20,DLE:0x20,EOT:0x20,
                          DC2:0x20,DC3:0x20,DC4:0x20,ERP:0x20,ERL:0x20})

    """UNT4 Packet Class."""
    def __init__(self, unt4str=None, 
                   prefix=None, header='', 
                   erp=False, erl=False, 
                   xx=None, yy=None, text=''):
        """Constructor.

        Parameters:

          unt4str -- packed unt4 string, overrides other params
          prefix -- prefix byte <DC2>, <DC3>, etc
          header -- header string eg 'R_F$'
          erp -- true for general clearing <ERP>
          erl -- true for <ERL>
          xx -- packet's column offset 0-99
          yy -- packet's row offset 0-99
          text -- packet content string

        """
        self.prefix = prefix    # <DC2>, <DC3>, etc
        self.header = header    # ident text string eg 'R_F$'
        self.erp = erp          # true for general clearing <ERP>
        self.erl = erl          # true for <ERL>
        self.xx = xx            # input column 0-99
        self.yy = yy            # input row 0-99
        self.text = text.translate(self.tmap)
        if unt4str is not None:
            self.unpack(unt4str)

    def unpack(self, unt4str=''):
        """Unpack the UNT4 data into this object."""
        if len(unt4str) > 2 and unt4str[0] == chr(self.SOH) \
                            and unt4str[-1] == chr(self.EOT):
            self.prefix = None
            newhead = u''
            newtext = u''
            self.erl = False
            self.erp = False
            head = True		# All text before STX is considered header
            stx = False
            dle = False
            dlebuf = u''
            i = 1
            packlen = len(unt4str) - 1
            while i < packlen:
                och = ord(unt4str[i])
                if och == self.STX:
                    stx = True
                    head = False
                elif och == self.DLE and stx:
                    dle = True
                elif dle:
                    dlebuf += unt4str[i]
                    if len(dlebuf) == 4:
                        dle = False
                elif head:
                    if och in (self.DC2, self.DC3, self.DC4):
                        self.prefix = och   # assume pfx before head text
                    else:
                        newhead += unt4str[i]
                elif stx:
                    if och == self.ERL:
                        self.erl = True
                    elif och == self.ERP:
                        self.erp = True
                    else:
                        newtext += unt4str[i]
                i += 1
            if len(dlebuf) == 4:
                self.xx = int(dlebuf[:2])
                self.yy = int(dlebuf[2:])
            self.header = newhead
            self.text = newtext

    def pack(self):
        """Return Omega Style UNT4 unicode string packet."""
        head = ''
        text = ''
        if self.erp:	# overrides any other message content
            text = chr(self.STX) + chr(self.ERP)
        else:
            head = self.header
            if self.prefix is not None:
                head = chr(self.prefix) + head
            if self.xx is not None and self.yy is not None:
                text += chr(self.DLE) + u'{0:02d}{1:02d}'.format(
                                              self.xx, self.yy)
            if self.text:
                text += self.text
            if self.erl:
                text += chr(self.ERL)
            if len(text) > 0:
                text = chr(self.STX) + text
        return chr(self.SOH) + head + text + chr(self.EOT)

# TCP/IP message receiver and socket server
socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer.request_queue_size = 4
class recvhandler(socketserver.BaseRequestHandler):
    def handle(self):
        """Receive message from TCP"""
        data = bytearray()
        while True:
            data += self.request.recv(64)
            if len(data) == 0:
                break
            while unt4.EOT in data:
                (buf, sep, data) = data.partition(bytes([unt4.EOT]))
                m = unt4(unt4str=(buf+sep).decode('utf-8','ignore'))
                if self.server.tbh is not None and m is not None:
                    self.server.tbh.update(m)
class receiver(socketserver.ThreadingMixIn, socketserver.TCPServer):
    def set_tableau(self, th=None):
        self.tbh = th

# Graphic renderer
class tableau(threading.Thread):
    def __init__(self, x, y, fba):
        threading.Thread.__init__(self)
        self.running = False
        self.__fb = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        fba = fba.strip().lstrip('\0@')
        self.__fba = ('\0'+fba).encode('ascii','ignore')
        self.__q = queue.Queue(maxsize=32)
        self.__lu = TIMEOUT+1
        self.__lt = True
        self.__w = x
        self.__h = y
        self.__d = {'DC':None, 'RH':None, 'BP':None}
        self.__cols = self.__w // GLW
        self.__rows = (self.__h - HDRGAP) // LINEH
        self.__cks = cairo.ImageSurface(cairo.FORMAT_A1, self.__w, self.__h)
        self.__ckc = cairo.Context(self.__cks)
        self.__ckc.set_operator(cairo.Operator.SOURCE)
        self.__ckc.set_line_width(0.75)
        self.__ckrot = math.pi/30.0
        self.__ckc.select_font_face(CKFONT)
        self.__ckc.set_font_size(CKFH)
        self.__ckf = cairo.ImageSurface.create_from_png(CKFACE)
        self.__ckop = cairo.ImageSurface.create_from_png(CKOPEN)
        self.__ckcp = cairo.ImageSurface.create_from_png(CKCLOSE)
        self.__txs = cairo.ImageSurface(cairo.FORMAT_A1, self.__w, self.__h)
        self.__txc = cairo.Context(self.__txs)
        self.__txc.set_operator(cairo.Operator.SOURCE)
        self.__fbglcache = {}
        self.__gls = cairo.ImageSurface(cairo.FORMAT_A1,
                                        GLH*GLPW, GLH*(GLSZ//GLPW))
        # read in font png and render to A1 glyph cache
        tmpc = cairo.Context(self.__gls)
        tmps = cairo.ImageSurface.create_from_png(GLSRC)
        tmpc.set_source_surface(tmps,0,0)
        tmpc.paint()
        self.__gls.flush()

    def update(self, msg=None):
        """Queue a tableau update."""
        try:
            self.__q.put_nowait(msg)
        except queue.Full:
            print('Message queue is full')
            return None

    def __clock_hand(self, a, l, w):
        """Draw a clock hand of length l from [0,0] rotated to a"""
        self.__ckc.save()
        self.__ckc.rotate(a*self.__ckrot)
        self.__ckc.move_to(0,-l)
        self.__ckc.line_to(0.5*w,0)
        self.__ckc.line_to(0,0.4*w)
        self.__ckc.line_to(-0.5*w,0)
        self.__ckc.line_to(0,-l)
        self.__ckc.fill()
        self.__ckc.restore()

    def __clock_secs(self, a, l, head=True):
        """Draw a seconds hand of length l from [0,0] rotated to a"""
        self.__ckc.save()
        self.__ckc.rotate(a*self.__ckrot)
        self.__ckc.move_to(0,0)
        self.__ckc.line_to(0,-l)
        if head:
            self.__ckc.line_to(1,-l+4)
            self.__ckc.line_to(0,-l+6)
            self.__ckc.line_to(1,-l+4)
            self.__ckc.line_to(0,-l)
        self.__ckc.stroke()
        self.__ckc.restore()

    def __clock_pip(self, s, x, y):
        """Place a top of minute clock pip blob at [x,y]."""
        self.__ckc.save()
        self.__ckc.rectangle(x, y, 10, 8)
        self.__ckc.clip()
        self.__ckc.set_source_surface(s, x, y)
        self.__ckc.paint()
        self.__ckc.restore()

    def __clock_text(self, c):
        """Draw string 'c' on clock info area"""
        self.__ckc.save()
        trefy = 41
        trefx = CKH+2
        tbw = self.__w-trefx
        tbh = 16	# really?
        self.__ckc.set_source_rgba(0,0,0,0)
        self.__ckc.rectangle(trefx,trefy-12,tbw, tbh)
        self.__ckc.fill_preserve()
        self.__ckc.clip()
        self.__ckc.set_source_rgba(0,0,0,1)
        fm = self.__ckc.text_extents(c)
        xo = trefx + 0.5*tbw - 0.5*fm.width
        self.__ckc.move_to(xo,trefy)
        self.__ckc.show_text(c)
        self.__ckc.restore()

    def __show_clock(self):
        """Re-draw clock and output to display."""
        ctr = [[0,0], [1,0], [2,0],
               [2,1], [1,1], [0,1]]
        nc = time.localtime()
        oft = ctr[nc.tm_yday % len(ctr)]	# 'screen saver'

        # Place background then add hands.
        self.__ckc.save()
        if not self.__lt:
            # clock was last frame output
            self.__ckc.rectangle(0, 0, CKH+2, CKH+1)
            self.__ckc.clip()
        self.__ckc.set_source_surface(self.__ckf, oft[0], oft[1])
        self.__ckc.paint()
        self.__ckc.restore()
        self.__ckc.save()
        self.__ckc.translate(oft[0]+0.5*CKH, oft[1]+0.5*CKH)
        self.__clock_hand(5*(nc.tm_hour%12)+nc.tm_min//12, 17, 6)
        self.__clock_hand(nc.tm_min, 25, 5)
        self.__clock_secs(min(59, nc.tm_sec), 32)
        self.__ckc.restore()

        # Add informative text when available.
        amsgno = (nc.tm_sec) % 60
        if amsgno in [40,0]:
            self.__clock_text('{} {}/{}'.format(
                    DAYS[nc.tm_wday], nc.tm_mday, nc.tm_mon))
            if amsgno == 40:
                for var in self.__d:	# clear out stale info
                    self.__d[var] = None
        elif amsgno == 10:
            if self.__d['DC'] is not None:
                self.__clock_text('{0:0.1f} {1}C'.format(
                              self.__d['DC'],chr(0xb0)))
        elif amsgno == 20:
            if self.__d['RH'] is not None:
                self.__clock_text('{0:0.0f} %rh'.format(
                              self.__d['RH']))
            else:
                self.__clock_text('{} {}/{}'.format(
                    DAYS[nc.tm_wday], nc.tm_mday, nc.tm_mon))
        elif amsgno == 30:
            if self.__d['BP'] is not None:
                self.__clock_text('{0:0.0f} hPa'.format(self.__d['BP']))
            else:
                self.__clock_text('{} {}/{}'.format(
                    DAYS[nc.tm_wday], nc.tm_mday, nc.tm_mon))

        # Add top of minute animation
        xo = CKH+2+8	# check position
        yo = 52
        if nc.tm_sec < 4 or nc.tm_sec > 49:
            if nc.tm_sec in [50,0]:	# 10/GO
                i = 0
                while i < 5:
                    self.__clock_pip(self.__ckop, xo+11*i, yo)
                    i+=1
            elif nc.tm_sec == 55:	# 5
                self.__clock_pip(self.__ckcp, xo, yo)
            elif nc.tm_sec == 56:	# 4
                self.__clock_pip(self.__ckcp, xo+11, yo)
            elif nc.tm_sec == 57:	# 3
                self.__clock_pip(self.__ckcp, xo+22, yo)
            elif nc.tm_sec == 58:	# 2
                self.__clock_pip(self.__ckcp, xo+33, yo)
            elif nc.tm_sec == 59:	# 1
                self.__clock_pip(self.__ckcp, xo+44, yo)
        else:
            self.__ckc.save()
            self.__ckc.set_source_rgba(0,0,0,0)
            self.__ckc.rectangle(xo,yo,self.__w-xo,12)
            self.__ckc.fill()
            self.__ckc.restore()

        # Write frame to display socket
        self.__cks.flush()
        try:
            self.__fb.sendto(self.__cks.get_data(), self.__fba)
            self.__lt = False
        except Exception as e:
            print('caprica: Error sending clock: ' + repr(e))

    def __render_char(self, c):
        """Use manual then fallback font to render a missing glyph."""
        sfile = 'data/unichr-{0:#07x}.png'.format(ord(c))
        if resource_exists(__name__, sfile):
            # use a custom bitmap
            try:
                self.__fbglcache[c] = cairo.ImageSurface.create_from_png(
                                      resource_filename(__name__, sfile))
                print('caprica: Loaded glyph \'{}\'from {}'.format(c, sfile))
            except Exception as s:
                print('caprica: Error reading glyph {} from {}: {}'.format(
                        c, sfile, repr(e)))
        if c not in self.__fbglcache:
            # use a sloppy rendering of the unifont glyph
            self.__fbglcache[c] = cairo.ImageSurface(cairo.FORMAT_A1, 6,8)
            ctx = cairo.Context(self.__fbglcache[c])
            ctx.select_font_face(FBFONT)
            fontmat = cairo.Matrix(xx=11.0, yy=10.0)
            ctx.set_font_matrix(fontmat)
            ctx.move_to(-1.0,7.0)
            ctx.show_text(c)
            self.__fbglcache[c].flush()

    def __place_char(self, c, x, y):
        cord = ord(c)
        self.__txc.save()
        self.__txc.rectangle(x,y,GLW,GLH)
        self.__txc.clip()

        if cord < GLSZ:
            yo = y-GLH*(cord//GLPW)
            xo = x-GLH*(cord%GLPW)
            self.__txc.set_source_surface(self.__gls, xo, yo)
            self.__txc.paint()
        else:
            if c not in self.__fbglcache:
                self.__render_char(c)
            self.__txc.set_source_surface(self.__fbglcache[c],x,y)
            self.__txc.paint()
           
        self.__txc.restore()

    def __erase_page(self):
        self.__txc.save()
        self.__txc.set_source_rgba(0,0,0,0)
        self.__txc.paint()
        self.__txc.restore()

    def __show_text(self, msg=None):
        """Update text frame and send to display."""
        ret = False
        if isinstance(msg, unt4):
            dirty = False
            if msg.erp:
                # General clearing
                ret = True
                dirty = True
                self.__erase_page()
            elif msg.yy is not None:
                # Positioned text

                # If re-displaying from the clock, blank whole page
                if self.__lu > TIMEOUT:
                    self.__erase_page()

                ret = True
                vo = LINEH * msg.yy
                if msg.yy > 1:
                    vo += HDRGAP
                ho = msg.xx * GLW
                if msg.yy > 1:	# all non-headers are upper-cased
                    msg.text = msg.text.upper() # THIS MAY NOT BE THE SAME LEN
                for c in msg.text:
                    self.__place_char(c, ho, vo)
                    ho += GLW
                    dirty = True
                if msg.erl:
                    self.__txc.save()
                    self.__txc.rectangle(ho,vo,self.__w-ho,GLH)
                    self.__txc.clip()
                    self.__txc.set_source_rgba(0,0,0,0)
                    self.__txc.paint() 
                    self.__txc.restore()
                    dirty = True
            elif msg.header in ['DC','RH','BP']:
                # Info message - temp, pressure, humidity
                nv = None
                try:
                    nv = float(msg.text)
                except:
                    pass
                self.__d[msg.header] = nv

            if dirty:
                # Write frame to display socket
                self.__txs.flush()
                try:
                    self.__fb.sendto(self.__txs.get_data(), self.__fba)
                    self.__lt = True
                except Exception as e:
                    print('caprica: Error sending text: ' + repr(e))
        return ret
        
    def run(self):
        self.running = True
        while self.running:
            try:
                m = self.__q.get(timeout=2.0)
                self.__q.task_done()
                if m is None:
                    # Process a clock tick notification
                    self.__lu += 1
                    if self.__lu > TIMEOUT:
                        self.__show_clock()
                else:
                    # Process a text update
                    if self.__show_text(m):
                        self.__lu = 0	# reset counter
            except queue.Empty:
                pass
            except Exception as e:
                print('caprica: Tableau exception: ' + repr(e))
                running = False

def main():
    # Check command line options
    parser = argparse.ArgumentParser(description='Galactica/DHI Replacement')
    parser.add_argument('-p', '--port',
                        help='DHI port number [' + str(DEFPORT) + ']',
                        type=int, default=DEFPORT)
    parser.add_argument('-d', '--display',
                        help='Display socket [' + str(DEFFB) + ']',
                        type=str, default=DEFFB)
    parser.add_argument('-x', '--width',
                        help='Display width in pixels [' + str(WIDTH) + ']',
                        type=int, default=WIDTH)
    parser.add_argument('-y', '--height',
                        help='Display height in pixels [' + str(HEIGHT) + ']',
                        type=int, default=HEIGHT)
    parser.add_argument('-v', '--version', help='print version',
                        action='version',
                        version='%(prog)s ' + VERSION)
    args = parser.parse_args()

    # Create tableau helper thread
    tbl = tableau(args.width, args.height, args.display)
    tbl.start()

    # Create dhi socket server helper thread
    dhi = receiver(('0.0.0.0', args.port), recvhandler)
    dhi.set_tableau(tbl)
    dhi_thread = threading.Thread(target=dhi.serve_forever)
    dhi_thread.daemon = True
    dhi_thread.start()

    # Register alarm handler
    def timeout(signum, frame):
        """Send a clock update to the tableau."""
        tbl.update()
    signal.signal(signal.SIGALRM, timeout)

    # Set alarm for slightly after top of second, then wait
    now=time.time()
    then=float(int(now)+2)-now+0.01
    signal.setitimer(signal.ITIMER_REAL,then,1.0)
    try:
        while True:
            signal.pause()
    finally:
        tbl.running = False
        dhi.shutdown()

if __name__ == '__main__':
    main()

