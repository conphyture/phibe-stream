# credits to code from: https://github.com/IanHarvey/bluepy/issues/53

# TODO: get all RR values?

from bluepy.bluepy.btle import Peripheral, ADDR_TYPE_RANDOM, AssignedNumbers
from pylsl import StreamInfo, StreamOutlet

import time, struct, argparse

# retrieve MAC address
parser = argparse.ArgumentParser(description='Stream phibe channels using LSL.')
parser.add_argument("device_mac", help="MAC address of the MAC device")
args = parser.parse_args()

# ugly global variable go retrieve value from delegate
last_chan1 = 0
last_chan2 = 0

# will likely interpolate data if greater than 1Hz
samplingrate = 100 

# create LSL StreamOutlet
print "creating LSL outlet for channel 1, sampling rate:", samplingrate, "Hz"
info_c1 = StreamInfo('hr','hr',1,samplingrate,'float32','conphyture-phibe-c1')
outlet_c1 = StreamOutlet(info_c1)

print "creating LSL outlet for channel 2, sampling rate:", samplingrate, "Hz"
info_c2 = StreamInfo('rr','rr',1,samplingrate,'float32','conphyture-phibe-c2')
outlet_c2 = StreamOutlet(info_c2)

class Board(Peripheral):
    def __init__(self, addr):
        # list of channels
        self.nbChans = 2
        self.chan = []
        # init channels
        # TODO: numpy...
        for i in range(self.nbChans):
            self.chan.append([])
        # current position
        self.head = 0
        self.leftover = ''

        print "connecting to device", addr
        Peripheral.__init__(self, addr)
        print "...connected"

    def advanceHead(self):
        self.head += 1
        if self.head >= self.nbChans:
            self.head = 0

    def addData(self, cHandle,data):

        
       
        # complete with previous values and reset
        data = self.leftover + data

        nb_bytes = len(data)

        print "nb", nb_bytes
        bytes_left = nb_bytes % 3
        print "left", bytes_left
        print "read", nb_bytes - bytes_left
        for i in range(0, nb_bytes - bytes_left, 3):
            dat = data[i:i+3]
            self.chan[self.head].append(to32(dat))

            print self.head,
            for c in dat:
                print "%#x" % ord(c),
            print
            
            self.advanceHead()
        # add cut to buffer
        self.leftover = data[-bytes_left:]

# takes a tab of 3 bytes, return int
# (from OpenBCI python repo)
def to32(packed):
    unpacked = struct.unpack('3B', packed)
    #3byte int in 2s compliment
    if (unpacked[0] >= 127):
      pre_fix = '\xFF'
    else:
      pre_fix = '\x00'
    packed = pre_fix + packed
    #unpack little endian(>) signed integer(i) (makes unpacking platform independent)
    myInt = struct.unpack('>i', packed)[0]
    return myInt

if __name__=="__main__":
    try:

        board = Board(args.device_mac)
        # enable something??
        board.writeCharacteristic(0x0025, '\1\0', False)  

        t0=time.time()
        board.delegate.handleNotification = board.addData

        last_c1 = 0
        last_c2 = 0
 
        while True:
            board.waitForNotifications(1./samplingrate)
            # ugly way to stream and free board current buffer
            for c1 in board.chan[0]:
                outlet_c1.push_sample([c1])
                last_c1 = c1
            board.chan[0] = []
            for c2 in board.chan[1]:
                outlet_c2.push_sample([last_chan2])
                last_c2 = c2
            board.chan[1] = []
            print last_c1, last_c2
            
    finally:
        if board:
            # way get ""
            try:
                board.disconnect()
                print "disconnected"
            except:
                # may get "ValueError: need more than 1 value to unpack"??
                print "error while disconnecting"
