"""Music structure generation and manipulation.

MIDI message bytes are defined by the `MMA MIDI Specifications`_ for the sake
of compatibility with the many synthesizers and applications that adhere.

The current implementation only uses MIDI channel 1, but there are actually
16 channels available. For instance, to send a note-on message to channel 2
instead of channel 1, the note-on status byte should be 0x91 instead of 0x90.
To send a control change to channel 16 instead of channel 1, the control status
byte should be 0xBF instead of 0xB0.

.. _MMA MIDI Specifications
   https://www.midi.org/specifications/category/reference-tables
"""

import music21
import numpy as np

N_PITCHES = 127
VELOCITY_LO = 0
VELOCITY_HI = 127
VELOCITY_LIMS = (VELOCITY_LO, VELOCITY_HI + 1)
"""Basic MIDI constants."""

STATUS_BYTES = dict(
    NOTE_ON=0x90,
    NOTE_OFF=0x80,
    CONTROL=0xB0,
)
CONTROL_BYTES = dict(
    PEDAL_SUSTAIN=0x40,
    PEDAL_PORTAMENTO=0x41,
    PEDAL_SOSTENUTO=0x42,
    PEDAL_SOFT=0x43,
    RESET_ALL_CONTROLLERS=0x79,
    ALL_NOTES_OFF=0x7B,
)
"""MIDI message (event) bytes."""

PITCH_LIMS = dict(
    midi=(0, 127),
    piano=(21, 108),
)
PITCH_RANGES = {name: np.arange(lim[0], lim[1] + 1)
                for name, lim in PITCH_LIMS.items()}
"""MIDI pitch (note number) limits and ranges for different instruments."""


def notation_to_notes(notation):
    """ Parse a notation string and return a list of Note objects.

    Args:
        notation (str): Melody notated in a music21-parsable string format.

    Returns:
        notes (list): Sequence of ``music21.note.Note`` objects.
    """
    sequence = music21.converter.parse(notation)
    notes = list(sequence.flat.getElementsByClass(music21.note.Note))
    return notes


def random_note(pitch=None, pitch_range='full', velocity=None,
                velocity_lims=VELOCITY_LIMS):
    """Return a ``music21.note.Note`` with specified or randomized attributes.

    TODO: Check music21 API and use existing functions as much as possible.
    ``music21.midi.translate`` has relevant functions but will need to
    implement MIDI note durations (i.e. event times passed with events).

    Args:
        pitch (int or str): Pitch of the returned ``music21.note.Note``.
            A MIDI note number or music21-parsable string. Randomly assigned
            if ``None`` (default).
        pitch_range (iterable or string): Vector of MIDI pitches for random
            selection. May be a key from ``PITCH_RANGES`` corresponding to a
            pre-defined range vector.
        velocity (int): Defined velocity. Randomly assigned if ``None``.
        velocity_lims (tuple): Range of velocities for random assignment.

    Returns:
        note (music21.note.Note): Note object with assigned properties.
    """

    if pitch is None:
        pitch_range = _key_check(PITCH_RANGES, pitch_range, 'lower')
        pitch = np.random.choice(pitch_range)
    if velocity is None:
        velocity = np.random.randint(*velocity_lims)
    note = music21.note.Note(pitch)
    note.volume.velocity = velocity
    return note


def random_chord(chord_size=3, pitch_range='midi', velocity=None,
                 velocity_lims=VELOCITY_LIMS, unique=True):
    """Return a music21 Chord object with random pitches and velocity.

    TODO: MIDI velocity (int) or normalized velocity (/1.0)

    Args:
        chord_size (int): Number of notes in the returned chord.
        pitch_range (iterable or str): Vector of MIDI pitches for
            random selection. May be a key from ``PITCH_RANGES``
            corresponding to a pre-defined range.
        velocity (int): MIDI velocity of the returned chord.
            Randomly assigned if ``None`` (default).
        velocity_lims (tuple): Range of velocities for random assignment.
        unique (bool): If `True`, no duplicate pitches in returned chord.

    Returns:
        chord (music21.chord.Chord): Chord object.
    """
    pitch_range = _key_check(PITCH_RANGES, pitch_range, 'lower')
    pitches = np.random.choice(pitch_range, chord_size, replace=not unique)
    notes = [random_note(pitch=p, velocity=velocity,
                         velocity_lims=velocity_lims) for p in pitches]
    chord = music21.chord.Chord(notes)
    return chord


def chord_to_velocity_vector(chord):
    """Return a MIDI velocity vector for a music21 Chord object.

    Args:
        chord (music21.chord.Chord): Chord object to convert to vector form.

    Returns:
        velocity_vector (np.ndarray): Vector of velocities of each MIDI pitch
    """
    chord_velocity = chord.volume.velocity
    if chord_velocity is None:
        chord_velocity = 1.0
    velocity_vector = midi_velocity_vector()
    velocity_vector[[(p.midi - 1) for p in chord.pitches]] = chord_velocity
    return velocity_vector


def note_to_velocity_vector(note):
    """Return a MIDI pitch vector for a music21 Note object."""
    velocity_vector = chord_to_velocity_vector(music21.chord.Chord([note]))
    return velocity_vector


def random_velocity_vector(pitches, pitch_range='midi', velocity=None,
                           velocity_lims=VELOCITY_LIMS):
    """Return a random velocity vector.

    Args:
        pitches (int): Number of pitches in the velocity vector.
        pitch_range (iterable or string): Vector of MIDI pitches for
            random selection.
        velocity (int): MIDI velocity of returned chord.
            Chosen randomly if ``None`` (default).
        velocity_lims (tuple): Limits for random assignment of velocity.
    Returns:
        velocity_vector (np.ndarray): Vector of velocities of each MIDI pitch
    """
    chord = random_chord(chord_size=pitches, pitch_range=pitch_range,
                         velocity=velocity, velocity_lims=velocity_lims)
    velocity_vector = chord_to_velocity_vector(chord)
    return velocity_vector


def midi_all_notes_off(midi_basic=False, pitch_range='midi'):
    """Return MIDI event(s) to turn off all notes in range.

    Args:
        midi_basic (bool): Switches MIDI event type to turn notes off.
            Use NOTE_OFF events for each note if True, and single
            ALL_NOTES_OFF event if False.
        pitch_range (Tuple[int]): Range of pitches for NOTE_OFF events, if used.
            Defaults to entire MIDI pitch range.
    """
    pitch_range = _key_check(PITCH_RANGES, pitch_range, 'lower')
    if midi_basic:
        pitches_off = np.zeros(N_PITCHES)
        pitches_off[slice(*pitch_range)] = 1
        return vector_to_midi_events(STATUS_BYTES['NOTE_OFF'], pitches_off)
    else:
        return np.array(((STATUS_BYTES['CONTROL'],
                          CONTROL_BYTES['ALL_NOTES_OFF'], 0),))


def vector_to_midi_events(status, velocity_vector):
    """ Return MIDI event parameters for given velocity vector.

    Status can be specified as one of the keys in ``STATUS_BYTES``.

    Args:
        status: The status parameter of the returned events.
        velocity_vector (np.ndarray): Vector of velocities of each MIDI pitch

    Returns:
        chord_events (np.ndarray): MIDI event parameters, one event per row.
    """
    status = _key_check(STATUS_BYTES, status, 'upper')
    pitches = np.flatnonzero(velocity_vector)
    velocities = velocity_vector[pitches] * VELOCITY_HI
    chord_events = np.zeros((3, len(pitches)), dtype=np.uint8)
    chord_events[0] = status
    chord_events[1] = pitches
    chord_events[2] = velocities
    chord_events = chord_events.transpose()
    return chord_events


def note_to_midi_onoff(note):
    """Returns MIDI note-on and note-off events for a music21 note.

    Args:
        note (music21.Note.note): The ``music21`` note to convert to events.
    """
    vector = note_to_velocity_vector(note)
    note_on = vector_to_midi_events(STATUS_BYTES['NOTE_ON'], vector)
    note_off = vector_to_midi_events(STATUS_BYTES['NOTE_OFF'], vector)
    return note_on, note_off


def continuous_controller(status, data_byte1):
    """Return a function that varies the second data byte of a MIDI event.

    Args:
        status (int or str): The MIDI status byte.
        data_byte1 (int or str): The first MIDI data byte.
    """
    status = _key_check(STATUS_BYTES, status, 'upper')
    def event(data_byte2):
        return (status, data_byte1, data_byte2)
    return event


def midi_velocity_vector():
    """Returns a velocity vector of zeros for all MIDI pitches."""
    return np.zeros(PITCH_RANGES['midi'][1])


def _key_check(dict_, key, case=None):
    """"""
    if case is not None:
        try:
            key = getattr(key, case)()
        except AttributeError:
            return key
    try:
        value = dict_[key]
        return value
    except KeyError:
        return key
