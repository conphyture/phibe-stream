# borrowed some code from OpenBCI repo...

from bluepy.bluepy.btle import Peripheral, ADDR_TYPE_RANDOM, AssignedNumbers
from pylsl import StreamInfo, StreamOutlet

import time, struct, argparse

# retrieve MAC address
parser = argparse.ArgumentParser(description='Stream phibe channels using LSL.')
parser.add_argument("device_mac", help="MAC address of the MAC device")
args = parser.parse_args()

# will likely interpolate data if greater than 1Hz
samplingrate = 64

# start of data packet
START_BYTE = 0xA0

# create LSL StreamOutlet
print "creating LSL outlet sampling rate:", samplingrate, "Hz"
info_phibe = StreamInfo('phi','phi',2,samplingrate,'float32','conphyture-phibe')
outlet_phibe = StreamOutlet(info_phibe, max_buffered=1)

class Board(Peripheral):
    def __init__(self, addr):
        # list of channels
        self.nbChans = 2
        self.buffer = ''
        # current position
        self.head = 0
        self.samples = []
        self.read_state = 0

        print "connecting to device", addr
        Peripheral.__init__(self, addr)
        print "...connected"

    # read n data from buffer -- if overflow, fill with 0
    # TODO: better overflow check
    def read(self, n):
      if self.head + n > len(self.buffer):
           print "Warning: buffer overflow" 
           return '0'*n
      b = self.buffer[self.head:self.head+n]
      self.head += n
      return b

    # empty buffer until current head position
    def cleanup(self):
      self.buffer=self.buffer[self.head:-1]
      self.head = 0

    # reset head position
    def reset(self):
      self.head = 0

    # how much left in buffer
    def getBufferSize(self):
        return len(self.buffer) - self.head

    # TODO
    def checkCRC(self, crc, packet_id, channel_data):
        return True

    """
    Parses buffer packet into PhiBeSample.
    Incoming Packet Structure:
    Start Byte(1)|Sample ID(1)|Channel Data(24)|CRC(1)
    0xA0|0-255|2, 3-byte signed ints|1 byte
    """
    def parse(self, max_bytes_to_skip=3000):

        for rep in xrange(max_bytes_to_skip):

          #Looking for start and save id when found
          if self.read_state == 0:
            # FIXME: preemptive overflow check
            if self.getBufferSize() < 9:
              return
            b = self.read(1)
            if struct.unpack('B', b)[0] == START_BYTE:
              if(rep != 0):
                print "Skipped", rep, "bytes before start found"
              packet_id = struct.unpack('B', self.read(1))[0] #packet id goes from 0-255

              self.read_state = 1

          elif self.read_state == 1:
            channel_data = []
            for c in xrange(self.nbChans):

              #3 byte ints
              literal_read = self.read(3)
              myInt = to32(literal_read) 
              channel_data.append(myInt)

            self.read_state = 2;

          elif self.read_state == 2:
            crc = struct.unpack('B', self.read(1))[0]
            if self.checkCRC(crc, packet_id, channel_data):
              sample = PhiBeSample(packet_id, channel_data)
              self.read_state = 0 #read next packet
              return sample
            else:
              print "Warning: Wrong CRC, discarded packet with id", packet_id

    # pushing (and processing) data to buffer
    def addData(self, cHandle,data):

        # complete with previous values and reset
        self.buffer = self.buffer + data

        # useless to parse anything if not enough data
        while self.getBufferSize() >= 9:
           print len(data), "new,", self.head, "/", len(self.buffer)
           sample = self.parse(len(self.buffer))
           if not sample:
               self.reset()
               print "reset"
               break
           else:
               print "add"
               #self.cleanup()
               self.samples.append(sample)


class PhiBeSample(object):
  """Object encapulsating a single sample from the PhiBe board."""
  def __init__(self, packet_id, channel_data):
    self.id = packet_id;
    self.channel_data = channel_data;

        
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
        # board.writeCharacteristic(0x0025, '\1\0', False)  

        board.delegate.handleNotification = board.addData

        while True:
            board.waitForNotifications(1./samplingrate)
            # ugly way to stream and free board current buffer
            for s in board.samples:
                print "push sample: ", s.id, "values:", s.channel_data
                outlet_phibe.push_sample(s.channel_data)
            board.samples = []
            
    finally:
        if board:
            # way get ""
            try:
                board.disconnect()
                print "disconnected"
            except:
                # may get "ValueError: need more than 1 value to unpack"??
                print "error while disconnecting"
