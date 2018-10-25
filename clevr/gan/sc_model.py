from __future__ import division
import os
import sys
import time
import math
from glob import glob
import tensorflow as tf
import numpy as np
import itertools
from six.moves import xrange
from tensorflow.examples.tutorials.mnist import input_data

from ops import *
from utils import *

def conv_out_size_same(size, stride):
  return int(math.ceil(float(size) / float(stride)))

def print_in_file(sstr):
  sys.stdout.write(str(sstr)+'\n')
  sys.stdout.flush()
  os.fsync(sys.stdout)

class DCGAN(object):
  def __init__(self, sess, *, data_str, d_iter, g_iter, f_iter, wdf_iter, gp_coef, full,
         input_height=108, input_width=108, crop=True,
         batch_size=64, sample_num = 64, output_height=64, output_width=64,
         z_dim=100, gf_dim=64, df_dim=64,
         gfc_dim=1024, dfc_dim=1024, c_dim=3, dataset_name='default',
         input_fname_pattern='*.png', checkpoint_dir=None, sample_dir=None, test_sample_dir=None,
         model_name='WGAN-GP', base_name='CNN', decay=True, cors='color'):
    """
    Args:
      sess: TensorFlow session
      batch_size: The size of batch. Should be specified before training.
      z_dim: (optional) Dimension of dim for Z. [100]
      gf_dim: (optional) Dimension of gen filters in first conv layer. [64]
      df_dim: (optional) Dimension of discrim filters in first conv layer. [64]
      gfc_dim: (optional) Dimension of gen units for for fully connected layer. [1024]
      dfc_dim: (optional) Dimension of discrim units for fully connected layer. [1024]
      c_dim: (optional) Dimension of image color. For grayscale input, set to 1. [3]
    """
    self.sess = sess
    self.crop = crop
    self.base_name = base_name
    self.batch_size = batch_size
    self.sample_num = sample_num

    self.d_iter = d_iter
    self.g_iter = g_iter
    self.gp_coef = gp_coef
    self.f_iter = f_iter
    self.wdf_iter = wdf_iter

    self.dataset_name = dataset_name
    self.data_str = data_str
    self.full = full.split('-')
    assert len(self.full) == 2
    self.color_set = self.full[0].split('.')
    self.shape_set = self.full[1].split('.')
    # print (self.color_set)
    # print (self.shape_set)

    self.universal_set_color = list(itertools.product(self.color_set, self.color_set))
    self.universal_set_shape = list(itertools.product(self.shape_set, self.shape_set))
    self.universal_set = list(itertools.product(self.universal_set_color, self.universal_set_shape))
    self.train_set = []
    self.delete_set = []
    self.excp_data = self.dataset_name.split('-')
    self.excp_data = [i.split('.') for i in self.excp_data]
    self.dis_data = []
    for x in self.excp_data:
      for i in x:
        self.dis_data.append(i.split('_'))
    self.excp_data = self.dis_data
    assert len(self.excp_data) % 2 == 0, "wrong exceptions, odd not allowed"
    for i in range(len(self.excp_data)):
      assert self.excp_data[i][0] in self.color_set and self.excp_data[i][1] in self.shape_set

    if cors == 'color':
      for i in range(len(self.excp_data)):
        if i%2 != 0: continue
        self.delete_set.append('%s.%s'%(self.excp_data[i][0], self.excp_data[i+1][0]))
    elif cors == 'shape':
      for i in range(len(self.excp_data)):
        if i%2 != 0: continue
        self.delete_set.append('%s.%s'%(self.excp_data[i][1], self.excp_data[i+1][1]))
    else:
      assert False, "please choose color or shape as CORS"
    # print (self.delete_set)

    for i in self.universal_set:
      if cors == 'color':
        if '%s.%s'%(i[0][0], i[0][1]) in self.delete_set:
          continue
      else:
        if '%s.%s'%(i[1][0], i[1][1]) in self.delete_set:
          continue
      self.train_set.append('%s_%s.%s_%s'%(i[0][0], i[1][0], i[0][1], i[1][1]))

    for i in range(len(self.excp_data)):
      if i%2 != 0: continue
      self.train_set.append('%s_%s.%s_%s'%(self.excp_data[i][0], self.excp_data[i][1], self.excp_data[i+1][0], self.excp_data[i+1][1]))
    print_in_file(len(self.train_set))
    self.dataset_config = self.train_set # dataset_name.split('-')
    self.input_height = input_height
    self.input_width = input_width
    self.output_height = output_height
    self.output_width = output_width

    self.z_dim = z_dim

    self.gf_dim = gf_dim
    self.df_dim = df_dim

    self.gfc_dim = gfc_dim
    self.dfc_dim = dfc_dim

    # batch normalization : deals with poor initialization helps gradient flow
    self.d_bn1 = batch_norm(name='d_bn1')
    self.d_bn2 = batch_norm(name='d_bn2')
    self.d_bn3 = batch_norm(name='d_bn3')

    if self.base_name == 'CNN':
      self.g_bn0 = batch_norm(name='g_bn0')
      self.g_bn1 = batch_norm(name='g_bn1')
      self.g_bn2 = batch_norm(name='g_bn2')
      self.g_bn3 = batch_norm(name='g_bn3')
      self.g_bn4 = batch_norm(name='g_bn4')
      self.g_bn5 = batch_norm(name='g_bn5')
      self.g_bn6 = batch_norm(name='g_bn6')

    self.input_fname_pattern = input_fname_pattern
    self.checkpoint_dir = checkpoint_dir
    self.model_name = model_name

    self.data = []
    for d_str in self.dataset_config:
      print_in_file(os.path.join(self.data_str, d_str, 'images/', self.input_fname_pattern))
      self.data.extend(glob(os.path.join(self.data_str, d_str, 'images/', self.input_fname_pattern)))

    print_in_file("We have %d images" % (len(self.data)))
    print_in_file(os.path.join(self.data_str, self.dataset_name, self.input_fname_pattern))
    imreadImg = imread(self.data[0]);
    if len(imreadImg.shape) >= 3: #check if image is a non-grayscale image by checking channel number
      self.c_dim = imread(self.data[0]).shape[-1]
      if self.c_dim != 3:
        print_in_file("color dimension is not 3, but %d"%(self.c_dim))
        self.c_dim = 3
    else:
      self.c_dim = 1

    self.grayscale = (self.c_dim == 1)
    self.decay = decay
    self.build_model()

  def build_model(self):
    self.learning_rate = tf.placeholder(tf.float32, shape=[], name='lr')

    image_dims = [self.output_height, self.output_width, self.c_dim]
    self.inputs = tf.placeholder(
      tf.float32, [self.batch_size] + image_dims, name='real_images')
    inputs = self.inputs

    self.z = tf.placeholder(
      tf.float32, [None, self.z_dim], name='z')
    self.z_sum = histogram_summary("z", self.z)
    self.x_ = tf.placeholder(
      tf.float32, [self.batch_size] + image_dims, name='fake_images') #!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

    self.G                  = self.generator(self.z, None, base_name=self.base_name)
    self.sampler            = self.sampler(self.z, None, base_name=self.base_name)

    self.D, self.D_logits   = self.discriminator(inputs, None, model_name=self.model_name, reuse=False)
    self.D_, self.D_logits_ = self.discriminator(self.G, None, model_name=self.model_name, reuse=True)

    self.d_sum = histogram_summary("d", self.D)
    self.d__sum = histogram_summary("d_", self.D_)
    self.G_sum = image_summary("G", self.G)

    def sigmoid_cross_entropy_with_logits(x, y):
      try:
        return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, labels=y)
      except:
        return tf.nn.sigmoid_cross_entropy_with_logits(logits=x, targets=y)
    
    if self.model_name == 'WGAN-GP':
      scale = self.gp_coef
      self.d_loss_real = tf.reduce_mean(self.D_logits)
      self.d_loss_fake = -tf.reduce_mean(self.D_logits_)

      self.d_loss_real_sum = scalar_summary("d_loss_real", self.d_loss_real)
      self.d_loss_fake_sum = scalar_summary("d_loss_fake", self.d_loss_fake)
      self.d_loss = tf.reduce_mean(self.D_logits) - tf.reduce_mean(self.D_logits_)
      self.g_loss = tf.reduce_mean(self.D_logits_)

      epsilon = tf.random_uniform([], 0.0, 1.0)
      x_hat = epsilon * self.inputs + (1 - epsilon) * self.G

      d_hat = self.discriminator(x_hat, None, model_name=self.model_name, reuse=True)[0]
      ddx = tf.gradients(d_hat, x_hat)[0]
      ddx = tf.sqrt(tf.reduce_sum(tf.square(ddx), axis=(1,2,3)))
      self.ddx = tf.reduce_mean(tf.square(ddx - 1.0) * scale)

      self.d_loss = self.d_loss + self.ddx

    self.g_loss_sum = scalar_summary("g_loss", self.g_loss)
    self.d_loss_sum = scalar_summary("d_loss", self.d_loss)

    t_vars = tf.trainable_variables()

    self.d_vars = [var for var in t_vars if 'discriminator' in var.name]
    self.g_vars = [var for var in t_vars if 'generator' in var.name]
    self.saver = tf.train.Saver(max_to_keep=None)

  def generate_samples(self, config):
    batch_idxs=15
    for idx in xrange(batch_idxs):
      sample_z = np.random.uniform(-1, 1, size=(self.sample_num , self.z_dim))
      samples = self.sess.run(
        self.sampler,
        feed_dict={
            self.z: sample_z,
        },
      )
      save_images(samples, image_manifold_size(samples.shape[0]),
            './{}/{:04d}.png'.format(config.test_sample_dir, idx))

  def train(self, config):
    d_optim = tf.train.AdamOptimizer(self.learning_rate, beta1=config.beta1) \
              .minimize(self.d_loss, var_list=self.d_vars)
    g_optim = tf.train.AdamOptimizer(self.learning_rate, beta1=config.beta1) \
              .minimize(self.g_loss, var_list=self.g_vars)
    try:
      tf.global_variables_initializer().run()
    except:
      tf.initialize_all_variables().run()

    self.g_sum = merge_summary([self.z_sum, self.d__sum,
      self.G_sum, self.d_loss_fake_sum, self.g_loss_sum])
    self.d_sum = merge_summary(
        [self.z_sum, self.d_sum, self.d_loss_real_sum, self.d_loss_sum])
    self.writer = SummaryWriter("./logs", self.sess.graph)

    sample_z = np.random.uniform(-1, 1, size=(self.sample_num , self.z_dim))
    
    sample_files = self.data[0:self.sample_num]
    sample = [
        get_image(sample_file,
                  input_height=self.input_height,
                  input_width=self.input_width,
                  resize_height=self.output_height,
                  resize_width=self.output_width,
                  crop=self.crop,
                  grayscale=self.grayscale) for sample_file in sample_files]

    if (self.grayscale):
      sample_inputs = np.reshape(np.array(sample).astype(np.float32), (self.batch_size, self.input_height, self.input_width, 1))
    else:
      sample_inputs = np.array(sample).astype(np.float32)
  
    counter = 1
    start_time = time.time()

    d_flags = 0
    lr = config.learning_rate
    for epoch in range(config.epoch):
      if epoch % (config.epoch/10) == 0 and self.decay:
        lr /= 2     
      batch_idxs = min(len(self.data), config.train_size) // config.batch_size
      data_idx = np.arange(len(self.data))
      random.shuffle(data_idx)
      self.data = [self.data[idx] for idx in data_idx]

      for idx in range(0, batch_idxs):
        if config.dataset == 'mnist':
          batch_images = self.data_X[idx*config.batch_size:(idx+1)*config.batch_size]
          batch_labels = self.data_y[idx*config.batch_size:(idx+1)*config.batch_size]
        else:
          batch_files = self.data[idx*config.batch_size:(idx+1)*config.batch_size]
          batch = [
              get_image(batch_file,
                        input_height=self.input_height,
                        input_width=self.input_width,
                        resize_height=self.output_height,
                        resize_width=self.output_width,
                        crop=self.crop,
                        grayscale=self.grayscale) for batch_file in batch_files]
          
          if self.grayscale:
            batch_images = np.reshape(np.array(batch).astype(np.float32), (self.batch_size, self.input_height, self.input_width, 1))
          else:
            batch_images = np.array(batch).astype(np.float32)

        batch_z = np.random.uniform(-1, 1, [config.batch_size, self.z_dim]) \
              .astype(np.float32)

        # Update D network
        if self.model_name == 'WGAN-GP':
          if counter < self.f_iter or counter % 300 == 0:
            d_iters = self.wdf_iter
          else:
            d_iters = self.d_iter
          g_iters = self.g_iter
        for _ in range(d_iters):
          _, summary_str = self.sess.run([d_optim, self.d_sum],
            feed_dict={ self.inputs: batch_images, self.z: batch_z,
                          self.learning_rate: lr })
          self.writer.add_summary(summary_str, counter)

        # Update G network
        for g_iter in range(g_iters):
          _, summary_str = self.sess.run([g_optim, self.g_sum],
            feed_dict={ self.z: batch_z, self.learning_rate: lr })
          self.writer.add_summary(summary_str, counter)

        errD_fake = self.d_loss_fake.eval({ self.z: batch_z })
        errD_real = self.d_loss_real.eval({ self.inputs: batch_images })
        errG = self.g_loss.eval({self.z: batch_z})

        counter += 1
        print_in_file("Epoch: [%2d] [%4d/%4d] time: %4.4f, d_loss: %.5f, g_loss: %.5f, d_real: %.5f, d_fake: %.5f" \
          % (epoch, idx, batch_idxs,
            time.time() - start_time, errD_fake+errD_real, errG, errD_real, errD_fake))

        if np.mod(counter, 100) == 2:
          samples, d_loss, g_loss = self.sess.run(
            [self.sampler, self.d_loss, self.g_loss],
            feed_dict={
                self.z: sample_z,
                self.inputs: sample_inputs,
            },
          )
          save_images(samples, image_manifold_size(samples.shape[0]),
                './{}/train_{:02d}_{:04d}.png'.format(config.sample_dir, epoch, idx))
          print_in_file("[Sample] d_loss: %.8f, g_loss: %.8f" % (d_loss, g_loss)) 

        if (np.mod(counter, 2500) == 0 and counter > 0):
          self.save(config.checkpoint_dir, counter)

  def discriminator(self, image, y=None, reuse=False, model_name='WGAN-GP'):
    with tf.variable_scope("discriminator") as scope:
      if reuse:
        scope.reuse_variables()
      if model_name == 'WGAN-GP':
        h0 = lrelu(conv2d(image, self.df_dim, name='d_h0_conv'))
        h1 = lrelu(self.d_bn1(conv2d(h0, self.df_dim*2, name='d_h1_conv')))
        h2 = lrelu(self.d_bn2(conv2d(h1, self.df_dim*4, name='d_h2_conv')))
        h3 = lrelu(self.d_bn3(conv2d(h2, self.df_dim*8, name='d_h3_conv')))
        h4 = lrelu(linear(tf.reshape(h3, [self.batch_size, -1]), 1024, 'd_h4_lin'))
        h5 = linear(h4, 1, 'd_h5_lin')
        return h5, h5

  def generator(self, z, y=None, base_name='CNN'):
    with tf.variable_scope("generator") as scope:
      if base_name == 'CNN': 
        s_h, s_w = self.output_height, self.output_width
        s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)
        s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)
        s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)
        s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2)
        s_h32, s_w32 = conv_out_size_same(s_h16, 2), conv_out_size_same(s_w16, 2)

        self.z_, self.h0_w, self.h0_b = linear(
            z, self.gf_dim*16*s_h32*s_w32, 'g_h0_lin', with_w=True)

        self.h0 = tf.reshape(
            self.z_, [-1, s_h32, s_w32, self.gf_dim * 16])
        h0 = tf.nn.relu(self.g_bn0(self.h0))

        self.h1, self.h1_w, self.h1_b = deconv2d(
            h0, [self.batch_size, s_h16, s_w16, self.gf_dim*8], name='g_h1', with_w=True)
        h1 = tf.nn.relu(self.g_bn1(self.h1))

        h2, self.h2_w, self.h2_b = deconv2d(
            h1, [self.batch_size, s_h8, s_w8, self.gf_dim*4], name='g_h2', with_w=True)
        h2 = tf.nn.relu(self.g_bn2(h2))

        h3, self.h3_w, self.h3_b = deconv2d(
            h2, [self.batch_size, s_h4, s_w4, self.gf_dim*2], name='g_h3', with_w=True)
        h3 = tf.nn.relu(self.g_bn3(h3))

        h4, self.h4_w, self.h4_b = deconv2d(
            h3, [self.batch_size, s_h2, s_w2, self.gf_dim], name='g_h4', with_w=True)
        h4 = tf.nn.relu(self.g_bn4(h4))

        h5, self.h5_w, self.h5_b = deconv2d(
            h4, [self.batch_size, s_h, s_w, self.c_dim], name='g_h5', with_w=True)
        return tf.nn.tanh(h5)

  def sampler(self, z, y=None, base_name='CNN'):
    with tf.variable_scope("generator") as scope:
      scope.reuse_variables()
      if base_name == 'CNN': 
        s_h, s_w = self.output_height, self.output_width
        s_h2, s_w2 = conv_out_size_same(s_h, 2), conv_out_size_same(s_w, 2)
        s_h4, s_w4 = conv_out_size_same(s_h2, 2), conv_out_size_same(s_w2, 2)
        s_h8, s_w8 = conv_out_size_same(s_h4, 2), conv_out_size_same(s_w4, 2)
        s_h16, s_w16 = conv_out_size_same(s_h8, 2), conv_out_size_same(s_w8, 2)
        s_h32, s_w32 = conv_out_size_same(s_h16, 2), conv_out_size_same(s_w16, 2)

        self.z_, self.h0_w, self.h0_b = linear(
            z, self.gf_dim*16*s_h32*s_w32, 'g_h0_lin', with_w=True)

        self.h0 = tf.reshape(
            self.z_, [-1, s_h32, s_w32, self.gf_dim * 16])
        h0 = tf.nn.relu(self.g_bn0(self.h0))

        self.h1, self.h1_w, self.h1_b = deconv2d(
            h0, [self.batch_size, s_h16, s_w16, self.gf_dim*8], name='g_h1', with_w=True)
        h1 = tf.nn.relu(self.g_bn1(self.h1))

        h2, self.h2_w, self.h2_b = deconv2d(
            h1, [self.batch_size, s_h8, s_w8, self.gf_dim*4], name='g_h2', with_w=True)
        h2 = tf.nn.relu(self.g_bn2(h2))

        h3, self.h3_w, self.h3_b = deconv2d(
            h2, [self.batch_size, s_h4, s_w4, self.gf_dim*2], name='g_h3', with_w=True)
        h3 = tf.nn.relu(self.g_bn3(h3))

        h4, self.h4_w, self.h4_b = deconv2d(
            h3, [self.batch_size, s_h2, s_w2, self.gf_dim], name='g_h4', with_w=True)
        h4 = tf.nn.relu(self.g_bn4(h4))

        h5, self.h5_w, self.h5_b = deconv2d(
            h4, [self.batch_size, s_h, s_w, self.c_dim], name='g_h5', with_w=True)
        return tf.nn.tanh(h5)

  @property
  def model_dir(self):
    return "{}_{}_{}_{}".format(
        self.dataset_name, self.batch_size,
        self.output_height, self.output_width)
      
  def save(self, checkpoint_dir, step):
    model_name = "GAN.model"
    checkpoint_dir = os.path.join(checkpoint_dir, self.model_dir)

    if not os.path.exists(checkpoint_dir):
      os.makedirs(checkpoint_dir)

    self.saver.save(self.sess,
            os.path.join(checkpoint_dir, model_name),
            global_step=step)

  def load(self, checkpoint_dir):
    import re
    print_in_file(" [*] Reading checkpoints...")
    checkpoint_dir = os.path.join(checkpoint_dir, self.model_dir)

    ckpt = tf.train.get_checkpoint_state(checkpoint_dir)
    if ckpt and ckpt.model_checkpoint_path:
      ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
      self.saver.restore(self.sess, os.path.join(checkpoint_dir, ckpt_name))
      counter = int(next(re.finditer("(\d+)(?!.*\d)",ckpt_name)).group(0))
      print_in_file(" [*] Success to read {}".format(ckpt_name))
      return True, counter
    else:
      print_in_file(" [*] Failed to find a checkpoint")
      return False, 0

