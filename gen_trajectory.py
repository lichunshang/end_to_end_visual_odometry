import data
import config
import model
import tools
import tensorflow as tf
import numpy as np
import os

dir_name = "trajectory_results"
kitti_seq = "06"

if kitti_seq in ["11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21"]:
    save_ground_truth = False
else:
    save_ground_truth = True

cfg = config.CamEvalConfig

tools.printf("Building eval model....")
inputs, lstm_initial_state, initial_poses, \
is_training, fc_outputs, se3_outputs, lstm_states = model.build_seq_model(cfg)

tools.printf("Loading training data...")
train_data_gen = data.StatefulDataGen(cfg, "/home/cs4li/Dev/KITTI/dataset/", [kitti_seq])

results_dir_path = os.path.join(config.save_path, dir_name)
if not os.path.exists(results_dir_path):
    os.makedirs(results_dir_path)

# ==== Read Model Checkpoints =====
restore_model_file = "/home/cs4li/Dev/end_to_end_visual_odometry/results/train_seq_20180408-09-58-14/model_epoch_checkpoint-45"

variable_to_load = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, "^(cnn_layer|rnn_layer|fc_layer).*")
tf_restore_saver = tf.train.Saver(variable_to_load)

with tf.Session() as sess:
    tools.printf("Restoring model weights from %s..." % restore_model_file)
    tf_restore_saver.restore(sess, restore_model_file)

    total_batches = train_data_gen.total_batches()
    tools.printf("Start evaluation loop...")

    curr_lstm_states = np.zeros([2, cfg.lstm_layers, cfg.batch_size, cfg.lstm_size])

    prediction = np.zeros([total_batches + 1, 7])
    ground_truth = np.zeros([total_batches + 1, 7])
    init_pose = np.array([[0., 0., 0., 1., 0., 0., 0.]], dtype=np.float32)

    while train_data_gen.has_next_batch():
        j_batch = train_data_gen.curr_batch()

        # get inputs
        _, _, batch_data, _, se3_ground_truth = train_data_gen.next_batch()

        # Run training session
        _curr_lstm_states, _se3_outputs = sess.run(
            [lstm_states, se3_outputs],
            feed_dict={
                inputs: batch_data,
                lstm_initial_state: curr_lstm_states,
                initial_poses: init_pose,
                is_training: False,
            },
        )
        curr_lstm_states = _curr_lstm_states
        init_pose = _se3_outputs[0]

        # print(curr_lstm_states)
        # print(init_pose)

        #
        # print(_se3_outputs)
        # print(se3_ground_truth)

        prediction[j_batch + 1, :] = _se3_outputs[-1, -1]
        ground_truth[j_batch + 1:] = se3_ground_truth[-1, -1]

        if j_batch % 100 == 0:
            tools.printf("Processed %.2f%%" % (train_data_gen.curr_batch() / train_data_gen.total_batches() * 100))

    np.save(os.path.join(results_dir_path, "trajectory_" + kitti_seq), prediction)
    if save_ground_truth:
        np.save(os.path.join(results_dir_path, "ground_truth_" + kitti_seq), ground_truth)
