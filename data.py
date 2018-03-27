import pykitti
import numpy as np
import config
import gc
import transformations


class StatefulDataGen(object):

    # Note some frames at the end of the sequence, and the
    # last sequence might be omitted to fit the examples
    # of timesteps x batch size8
    def __init__(self, base_dir, sequences):
        self.truncated_seq_sizes = []
        self.end_of_sequence_indices = []
        self.curr_batch_idx = 0

        total_num_examples = 0

        for seq in sequences:
            seq_data = pykitti.odometry(base_dir, seq)
            num_frames = len(seq_data.poses)

            # less than timesteps number of frames will be discarded
            num_examples = (num_frames - 1) // config.timesteps
            self.truncated_seq_sizes.append(num_examples * config.timesteps + 1)
            total_num_examples += num_examples

        # less than batch size number of examples will be discarded
        self.total_batch_count = total_num_examples // config.batch_size
        # +1 adjusts for the extra image in the last time step
        total_timesteps = self.total_batch_count * (config.timesteps + 1)

        # since some examples will be discarded, readjust the truncated_seq_sizes
        deleted_frames = (total_num_examples - self.total_batch_count * config.batch_size) * config.timesteps
        for i in range(len(self.truncated_seq_sizes) - 1, -1, -1):
            if self.truncated_seq_sizes[i] > deleted_frames:
                self.truncated_seq_sizes[i] -= deleted_frames
                break
            else:
                self.truncated_seq_sizes[i] = 0
                deleted_frames -= self.truncated_seq_sizes[i]

        # for storing all training
        self.input_frames = np.zeros(
            [total_timesteps, config.batch_size, config.input_channels, config.input_height, config.input_width],
            dtype=np.uint8)
        poses_wrt_g = np.zeros([total_timesteps, config.batch_size, 4, 4], dtype=np.float32)  # ground truth poses

        num_image_loaded = 0
        for i_seq, seq in enumerate(sequences):
            seq_data = pykitti.odometry(base_dir, seq)
            length = self.truncated_seq_sizes[i_seq]

            for i_img in range(length):

                if i_img % 100 == 0:
                    print("Loading sequence %s %.1f%% " % (seq, (i_img / length) * 100))

                i = num_image_loaded % total_timesteps
                j = num_image_loaded // total_timesteps

                # swap axis to channels first
                img = seq_data.get_cam0(i_img)
                img = img.resize((config.input_width, config.input_height))
                img = np.array(img)
                img = np.reshape(img, [img.shape[0], img.shape[1], config.input_channels])
                img = np.moveaxis(np.array(img), 2, 0)
                pose = seq_data.poses[i_img]

                self.input_frames[i, j] = img
                poses_wrt_g[i, j] = pose
                num_image_loaded += 1

                # if at end of a sequence
                if i_img != 0 and i_img != length - 1 and i_img % config.timesteps == 0:
                    i = num_image_loaded % total_timesteps
                    j = num_image_loaded // total_timesteps
                    self.input_frames[i, j] = img
                    poses_wrt_g[i, j] = pose

                    # save this index, so we know where the next sequence begins
                    self.end_of_sequence_indices.append((i, j,))

                    num_image_loaded += 1

                gc.collect()  # force garbage collection

        # make sure the all of examples are fully loaded, just to detect bugs
        assert (num_image_loaded == total_timesteps * config.batch_size)

        # now convert all the ground truth from 4x4 to xyz + quat, this is after the SE3 layer
        self.se3_ground_truth = np.zeros([total_timesteps, config.batch_size, 7], dtype=np.float32)
        for i in range(0, self.se3_ground_truth.shape[0]):
            for j in range(0, self.se3_ground_truth.shape[1]):
                translation = transformations.translation_from_matrix(poses_wrt_g[i, j])
                quat = transformations.quaternion_from_matrix(poses_wrt_g[i, j])
                self.se3_ground_truth[i, j] = np.concatenate([translation, quat])

        # extract the relative transformation between frames after the fully connected layer
        self.fc_ground_truth = np.zeros([total_timesteps, config.batch_size, 6], dtype=np.float32)
        # going through rows, then columns
        for i in range(0, self.fc_ground_truth.shape[0]):
            for j in range(0, self.fc_ground_truth.shape[1]):

                # always identity at the beginning of the sequence
                if i % (config.timesteps + 1) == 0:
                    m = transformations.identity_matrix()
                else:
                    m = np.dot(np.linalg.inv(poses_wrt_g[i - 1, j]), poses_wrt_g[i, j])  # double check

                translation = transformations.translation_from_matrix(m)
                ypr = transformations.euler_from_matrix(m, axes="rzyx")
                self.fc_ground_truth[i, j] = np.concatenate([translation, ypr])  # double check

        print("All data loaded, batches_size=%d, timesteps=%d, num_batches=%d" % (
            config.batch_size, config.timesteps, self.total_batch_count))

    def next_batch(self):
        i_b = self.curr_batch_idx
        n = config.timesteps + 1  # number of frames in an example
        # slice a batch from huge matrix of training data
        batch = self.input_frames[i_b * n: (i_b + 1) * n, :, :, :, :]
        batch = np.divide(batch, 255.0, dtype=np.float32)  # ensure float32

        se3_ground_truth = self.se3_ground_truth[i_b * n: (i_b + 1) * n, :, :]
        fc_ground_truth = self.fc_ground_truth[i_b * n: (i_b + 1) * n, :, :]
        init_poses = se3_ground_truth[0, :, :]

        # decide if we should propagate states
        i = self.curr_batch_idx * n
        reset_state = np.zeros([config.batch_size], dtype=np.uint8)
        for j in range(0, config.batch_size):
            if (i, j,) in self.end_of_sequence_indices:
                reset_state[j] = 1
            else:
                reset_state[j] = 0

        self.curr_batch_idx += 1

        return init_poses, reset_state, batch, fc_ground_truth, se3_ground_truth

    def has_next_batch(self):
        return self.curr_batch_idx < self.total_batch_count

    def next_epoch(self):
        self.curr_batch_idx = 0
