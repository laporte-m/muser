"""Input and output of music data, including `.wav` and live MIDI.

Low-latency audio connectivity is provided by python-rtmidi via JACK.
"""

import sys
import time
import binascii
import struct
import numpy as np
import rtmidi
import music21
from scipy.io import wavfile

SND_DTYPES = {'int16': 16, 'int32': 32}
"""dict: Data types that SciPy can import from `.wav`"""

NOTE_ON = 0x90
NOTE_OFF = 0x80
""" MIDI parameters. """


def init_midi_out():
    """  """
    midi_out = rtmidi.MidiOut()
    midi_in = rtmidi.MidiIn()

    ports_out = midi_out.get_ports()
    ports_in = midi_in.get_ports()

    if ports_out:
        midi_out.open_port(0)
    else:
        midi_out.open_virtual_port("Virtual Port Out 0")

    if ports_in:
        midi_in.open_port(0)
    else:
        midi_in.open_virtual_port("Virtual Port In 0")

    return midi_out, midi_in


def get_send_events(midi_out):
    """ Returns a function that sends MIDI events through rtmidi.

    Parameters:
        midi_out (rtmidi.MidiOut):

    Returns:
        send_events (function):
    """

    def send_events(events, loop=1):
        """ Send a series of MIDI events out through rtmidi.

        Parameters:
            events (list): Tuples of tuple for MIDI event and subsequent pause.
            loop (int): Number of times to repeat send of events.

        Returns:
            None
        """
        while True:
            for event, pause in events:
                midi_out.send_message(event)
                time.sleep(pause)
                # TODO: offset instead of pause (simpler concurrent notes)
            if loop > 1:
                loop -= 1
            else:
                break

    return send_events


def to_midi_note(music21_note):
    """ Return tuples specifying on/off MIDI note events for a music21 Note.

    Parameters:
        music21_note (music21.note.Note): The Note object for conversion

    Returns:
        note_on (tuple): Parameters for the MIDI NOTE_ON event
        note_off (tuple): Parameters for the MIDI NOTE_OFF event
    """
    midi_pitch = music21_note.pitch.midi
    velocity = music21_note.volume.velocity
    note_on = (NOTE_ON, midi_pitch, velocity)
    note_off = (NOTE_OFF, midi_pitch, velocity)

    return note_on, note_off


def to_midi_notes(music21_notes):
    """ Convert music21 notes to tuples specifying MIDI events.

    Parameters:
        music21_notes (list): List of music21 Note objects to be converted

    Returns:
        midi_notes (list): Pairs of tuples specifying on/off MIDI note events.
    """
    midi_notes = [to_midi_note(note) for note in music21_notes]

    return midi_notes


def report_midi_event(event, last_frame_time=0, out=sys.stdout):
    """ Print details of a midi event.

    Parameters:
        event ():
        last_frame_time (int):
        out ():
    """
    offset, indata = event
    #print(struct.unpack(str(len(indata))+'B\n', indata))
    try:
        status, pitch, vel = struct.unpack('3B', indata)
    except struct.error:

        return
    rprt = "{0} + {1}:\t0x{2}\n".format(last_frame_time,offset,
                                     binascii.hexlify(indata).decode())
    #rprt += "indata: {0}\n".format(indata)
    rprt += "status: {0},\tpitch: {1},\tvel.: {2}\n".format(status, pitch, vel)
    #rprt += "repacked: {0}".format(struct.pack('3B', status, pitch, vel))
    rprt += "\n"
    out.write(rprt)


def get_to_sample_index(sample_frq):
    """Return function that converts time to sample index for given sample rate.

    Parameters:
        sample_frq (int):

    Returns:
        to_sample_index (function):
    """
    def to_sample_index(time):
        """ Return sample index corresponding to a given time.

        Parameters:
            time (float, int):

        Returns:

        """
        def to_sample(time):
            try:
                return int(time * sample_frq)
            except TypeError:  # time not specified or specified badly
                e = "Real local endpoints must be specified! (t_endp)"
                raise TypeError(e)
        try:
            samples = [to_sample(t) for t in time]

            return samples

        except TypeError:  # time not iterable
            sample = to_sample(time)

            return sample

    return to_sample_index


def unit_snd(snd, factor=None):
    """ Scale elements of an array of wav data from -1 to 1.

    Default factor is determined from `snd.dtype`, corresponding to the format imported by `scipy.io.wavfile`. Can scale other types of data if factor is appropriately specified and data object can be scaled element-wise with the division operator, as for np.ndarray.

    Parameters:
        snd (np.ndarray): Data (audio from `.wav`) to be scaled.
        factor (int): Divide elements of snd by this number.

    Returns:
        scaled (np.ndarray): Same shape as snd, with elements scaled by factor.
    """
    if factor is None:
        factor = 2. ** (SND_DTYPES[snd.dtype.name] - 1)
    scaled = snd / factor

    return scaled


def wav_read_scaled(wavfile_name):
    """ Return contents of `.wav` scaled from -1 to 1.

    Parameters:
        wavfile_name (str):

    Returns:
        sample_rate (int):
        snd (np.ndarray):
    """
    sample_rate, snd = wavfile.read(wavfile_name)
    snd = unit_snd(snd)

    return sample_rate, snd