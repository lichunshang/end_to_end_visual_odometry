import tensorflow as tf
import model
import losses
import numpy as np
import tools
from config import *
import data

with tf.device("/cpu:0"):
    data_generator = data.StatefulDataGen("/home/lichunshang/Dev/KITTI/dataset/", ["00"])

# =================== INPUTS ========================
# All time major
inputs = tf.placeholder(tf.float32, name="inputs",
                        shape=[timesteps + 1, batch_size, input_channels, input_width, input_height])

# init LSTM states, 2 (cell + hidden states), 2 layers, batch size, and 1024 state size
lstm_init_state = tf.placeholder(tf.float32, name="lstm_init_state", shape=[2, lstm_layers, batch_size, lstm_size])

# init poses, initial position for each example in the batch
initial_poses = tf.placeholder(tf.float32, name="initial_poses", shape=[batch_size, 7])

# 7 for translation + quat
se3_labels = tf.placeholder(tf.float32, name="se3_labels", shape=[timesteps, batch_size, 7])

# 6 for translation + rpy, labels not needed for covars
fc_labels = tf.placeholder(tf.float32, name="se3_labels", shape=[timesteps, batch_size, 6])

# dynamic learning rates
se3_lr = tf.placeholder(tf.float32, name="se3_lr", shape=[])
fc_lr = tf.placeholder(tf.float32, name="fc_lr", shape=[])

# =================== MODEL + LOSSES + Optimizer ========================
fc_outputs, se3_outputs, lstm_states = model.build_training_model(inputs, lstm_init_state, initial_poses)

with tf.device("/gpu:0"):
    with tf.variable_scope("Losses"):
        se3_losses = losses.se3_losses(se3_outputs, se3_labels, k)
        fc_losses = losses.fc_losses(fc_outputs, fc_labels)

with tf.variable_scope("Optimizer"):
    with tf.device("/gpu:0"):
        se3_trainer = tf.train.AdamOptimizer(learning_rate=se3_lr).minimize(se3_outputs)
    with tf.device("/gpu:0"):
        fc_trainer = tf.train.AdamOptimizer(learning_rate=fc_lr).minimize(fc_outputs)

# =================== TRAINING ========================
with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())

    # Visualization
    writer = tf.summary.FileWriter('graph_viz/')
    writer.add_graph(tf.get_default_graph())

    se3_losses_history = []
    fc_losses_history = []

    for i_epoch in range(num_epochs):

        curr_lstm_states = np.zeros([2, lstm_layers, batch_size, lstm_size])

        while (data_generator.has_next_batch()):
            init_poses, reset_state, batch_data, \
            fc_ground_truth, se3_ground_truth = data_generator.next_batch()

            curr_lstm_states = tools.reset_select_lstm_state(curr_lstm_states, reset_state)

            _se3_losses, _se3_trainer, _curr_lstm_states = sess.run(
                [se3_losses, se3_trainer, lstm_states, ],
                feed_dict={
                    inputs: batch_data,
                    se3_labels: se3_ground_truth,
                    lstm_init_state: curr_lstm_states,
                    initial_poses: init_poses,
                    se3_lr: 0.001,
                }
            )
            se3_losses_history.append(_se3_losses)
            curr_lstm_states = _curr_lstm_states

            _fc_losses, _fc_trainer, _curr_lstm_states = sess.run(
                [fc_losses, fc_trainer, lstm_states, ],
                feed_dict={
                    inputs: batch_data,
                    fc_labels: fc_ground_truth,
                    lstm_init_state: curr_lstm_states,
                    initial_poses: init_poses,
                    fc_lr: 0.001,
                }
            )
            fc_losses_history.append(_fc_losses)

            curr_lstm_states = _curr_lstm_states

            # print stats
            print("se_loss: %f, fc_loss: %f" % (_se3_losses, _fc_losses))
