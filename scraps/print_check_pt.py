from tensorflow.python.tools import inspect_checkpoint as chkp

restore_model_file = "/home/cs4li/Dev/end_to_end_odometry/results/train_seq_20180729-10-49-24_fixnn_usenncovar_nogt/model_epoch_checkpoint-199"

chkp.print_tensors_in_checkpoint_file(restore_model_file, tensor_name='',
                                      all_tensors=True, all_tensor_names=True)
