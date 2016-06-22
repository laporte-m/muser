""" Learn to predict notes from FFT data.

Send notes to MIDI synthesizer, then calculate FFT for resulting audio; FFT becomes input for neural network, while the known notes that produced it are training outputs.

Starting with input FFT length equal to JACK buffer size, output vector with length 88 corresponding to all notes on a standard piano, and one hidden layer. By heuristics, number of neurons in single hidden layer likely between 88 and 512.

Each note played will produce many buffers worth of audio data. FFT should vary over the duration of the note, but this can be minimized by disabling certain features of the synthesizer. Initially, play isolated notes/chords and take the FFTs at maximum amplitude as inputs, or use an average over the duration. As more complex examples are investigated, will need more nuanced algorithm to isolate harmonic features.

Currently using `rtmidi` to send notes to the synthesizer, as this is much simpler to time without messing with threading and buffer offsets through `jack`, which now monitors audio buffers output from the synthesizer. Hope to eliminate one of these dependencies eventually.

TODO: Switch to TensorFlow batch 1D FFT when supported by OpenCL
"""

import numpy as np
import tensorflow as tf
import muser.iodata
import muser.sequencer
import muser.utils
import muser.fft
import matplotlib.pyplot as plt
import scipy.io.wavfile

N_MIDI_PITCHES = 127

# Synthesizer MIDI ports
synth_outports = ["Pianoteq55:out_1", "Pianoteq55:out_2"]
synth_midi_in = "Pianoteq55:midi_in"

channels = len(synth_outports)

# `jack` initialization
audio_client = muser.iodata.init_jack_client(inports=channels)
buffer_size = audio_client.blocksize
sample_rate = audio_client.samplerate

# `rtmidi` initialization
rtmidi_out = muser.iodata.init_rtmidi_out()
send_events = muser.iodata.get_send_events(rtmidi_out)

# Training parameters
chord_size = 1
batch_size = 2
batches = 2
learning_rate = 0.001

# storage of results
# TODO: velocity vectors
rec_dtype = np.dtype([('pitch_vector', np.uint8, N_MIDI_PITCHES),
                      ('buffers', object)])
recordings = np.ndarray([batches, batch_size], dtype=rec_dtype)
buffers = np.ndarray([channels, 0, buffer_size])

# generate note batches
random_pitch_vector = muser.sequencer.random_pitch_vector
recordings['pitch_vector'] = muser.utils.get_batches(random_pitch_vector,
                                                      batches, batch_size,
                                                      [chord_size])

# temporary and control variables used by the `jack` monitor
buffer_ = np.ndarray([channels, 1, buffer_size])
note_toggle = False

# `jack` monitor
@audio_client.set_process_callback
def process(frames):
    global buffers
    global buffer_
    global note_toggle
    if note_toggle:
        for ch in range(channels):
            buffer_[ch] = audio_client.inports[ch].get_array()
        buffers = np.append(buffers, buffer_, axis=1)

audio_client.activate()
try:
    # connect synthesizer stereo audio outputs to `jack` client inputs
    for port_pair in zip(synth_outports, audio_client.inports):
        audio_client.connect(*port_pair)

    for batch in recordings:
        for recording in batch:
            pitch_vector = recording['pitch_vector']
            events = muser.iodata.to_midi_note_events(pitch_vector)
            note_toggle = True
            send_events(events[0])
            while np.any(buffer_[0]) or buffers.shape[1] < 10:
                # `jack` listening through `process()`
                # wait for silence, except during first few buffers
                pass
            note_toggle = False
            send_events(events[1])
            recording['buffers'] = buffers
            buffers = np.ndarray([channels, 0, buffer_size])

except (KeyboardInterrupt, SystemExit):
    note_toggle = False
    print('\nUser or system interrupt, dismantling JACK clients!')
    # synthesizer
    muser.iodata.midi_all_notes_off(rtmidi_out, midi_basic=True)
    # close `rtmidi` and `jack` clients
    del rtmidi_out
    muser.iodata.del_jack_client(audio_client)
    raise

# store audio results
recordings.dump('recordings.pickle')

for b, batch in enumerate(recordings):
    for p, recording in enumerate(batch):
        snd = muser.iodata.buffers_to_snd(recording['buffers'])
        wavfile_name = 'b{}p{}.wav'.format(b, p)
        scipy.io.wavfile.write(wavfile_name, sample_rate, snd)


quit()

# Neural network parameters
inputs = buffer_size
hidden1_n = 300
outputs = 88

# Input placeholder variables
x = tf.placeholder(tf.float32, shape=[None, inputs])

with tf.name_scope('hidden1'):
    weights = tf.Variable(
        tf.truncated_normal([inputs, hidden1_n],
                            stddev=1.0 / np.sqrt(float(inputs))),
        name='weights')
    biases = tf.Variable(tf.zeros([hidden1_n]), name='biases')
    hidden1 = tf.nn.relu(tf.matmul(x, weights) + biases)

with tf.name_scope('output'):
    weights = tf.Variable(
        tf.truncated_normal([hidden1_n, outputs],
                            stddev=1.0 / np.sqrt(float(hidden1_n))),
        name='weights')
    biases = tf.Variable(tf.zeros([outputs]),
                         name='biases')
    output = tf.matmul(hidden1, weights) + biases

# compute cost
cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(output, labels,
                                                               name='crossent')
cost = tf.reduce_mean(cross_entropy, name='crossent_mean')

# prepare training optimizer
optimizer = tf.train.GradientDescentOptimizer(learning_rate)
train_op = optimizer.minimize(cost)


with tf.Session() as sess:
    with tf.device("/cpu:0"):
        pass
