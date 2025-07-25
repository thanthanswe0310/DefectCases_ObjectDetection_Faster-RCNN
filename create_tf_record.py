# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

r"""Convert the Oxford pet dataset to TFRecord for object_detection.

See: O. M. Parkhi, A. Vedaldi, A. Zisserman, C. V. Jawahar
     Cats and Dogs
     IEEE Conference on Computer Vision and Pattern Recognition, 2012
     http://www.robots.ox.ac.uk/~vgg/data/pets/

Example usage:
    ./create_pet_tf_record --data_dir=/home/user/pet \
        --output_dir=/home/user/pet/output
"""

import hashlib
import io
import logging
import os
import random
import re
import sys
import numpy as np
from lxml import etree
import PIL.Image

import tensorflow.compat.v1 as tf

from object_detection.utils import dataset_util
from object_detection.utils import label_map_util
import warnings
warnings.simplefilter('ignore')
def dict_to_tf_example(data,
                       label_map_dict,
                       image_subdirectory,
                       ignore_difficult_instances=False):
  """Convert XML derived dict to tf.Example proto.

  Notice that this function normalizes the bounding box coordinates provided
  by the raw data.

  Args:
    data: dict holding PASCAL XML fields for a single image (obtained by
      running dataset_util.recursive_parse_xml_to_dict)
    label_map_dict: A map from string label names to integers ids.
    image_subdirectory: String specifying subdirectory within the
      Pascal dataset directory holding the actual image data.
    ignore_difficult_instances: Whether to skip difficult instances in the
      dataset  (default: False).

  Returns:
    example: The converted tf.Example.

  Raises:
    ValueError: if the image pointed to by data['filename'] is not a valid JPEG
  """
  img_path = os.path.join(image_subdirectory, data['filename'])
  img_path.encode('utf-8', 'backslashreplace').decode().replace("\\", "/")
  rename_img_path = img_path.split('.')[0]
  #print(f"rename_img_path:{rename_img_path}")
  with tf.gfile.GFile(img_path, 'rb') as fid:
    encoded_jpg = fid.read()
  encoded_jpg_io = io.BytesIO(encoded_jpg)
  image = PIL.Image.open(encoded_jpg_io)


  '''
  #print(f"image mode : {image.mode }")
  #RGB확인완료
  r,g,b = image.split()
  r.save(os.path.join(f"{rename_img_path}_r.jpg"))
  g.save(os.path.join(f"{rename_img_path}_g.jpg"))
  b.save(os.path.join(f"{rename_img_path}_b.jpg"))
  rbg_img = np.array(image)

  image_r = rbg_img[:,:,0]
  image_g = rbg_img[:,:,1]
  image_b = rbg_img[:,:,2]
  print(f"rename : {rename_img_path}_r.jpg")

  PIL.Image.fromarray(image_r)
  PIL.Image.fromarray(image_g)
  PIL.Image.fromarray(image_b)

  image_r.save(os.path.join(f"{rename_img_path}_r.jpg"))
  image_g.save(os.path.join(f"{rename_img_path}_g.jpg"))
  image_b.save(os.path.join(f"{rename_img_path}_b.jpg"))
  '''


  if image.format != 'JPEG':
    raise ValueError('Image format not JPEG')
  key = hashlib.sha256(encoded_jpg).hexdigest()

  width = int(data['size']['width'])
  height = int(data['size']['height'])

  xmin = []
  ymin = []
  xmax = []
  ymax = []
  classes = []
  classes_text = []
  truncated = []
  poses = []
  difficult_obj = []
  if 'object' in data:
    for obj in data['object']:
      difficult = bool(int(obj['difficult']))
      if ignore_difficult_instances and difficult:
        continue

      difficult_obj.append(int(difficult))

      xmin.append(float(obj['bndbox']['xmin']) / width)
      ymin.append(float(obj['bndbox']['ymin']) / height)
      xmax.append(float(obj['bndbox']['xmax']) / width)
      ymax.append(float(obj['bndbox']['ymax']) / height)
      classes_text.append(obj['name'].encode('utf-8'))
      classes.append(label_map_dict[obj['name']])
      truncated.append(int(obj['truncated']))
      poses.append(obj['pose'].encode('utf-8'))

  example = tf.train.Example(features=tf.train.Features(feature={
      'image/height': dataset_util.int64_feature(height),
      'image/width': dataset_util.int64_feature(width),
      'image/filename': dataset_util.bytes_feature(
          data['filename'].encode('utf-8')),
      'image/source_id': dataset_util.bytes_feature(
          data['filename'].encode('utf-8')),
      'image/key/sha256': dataset_util.bytes_feature(key.encode('utf-8')),
      'image/encoded': dataset_util.bytes_feature(encoded_jpg),
      'image/format': dataset_util.bytes_feature('jpeg'.encode('utf-8')),
      'image/object/bbox/xmin': dataset_util.float_list_feature(xmin),
      'image/object/bbox/xmax': dataset_util.float_list_feature(xmax),
      'image/object/bbox/ymin': dataset_util.float_list_feature(ymin),
      'image/object/bbox/ymax': dataset_util.float_list_feature(ymax),
      'image/object/class/text': dataset_util.bytes_list_feature(classes_text),
      'image/object/class/label': dataset_util.int64_list_feature(classes),
      'image/object/difficult': dataset_util.int64_list_feature(difficult_obj),
      'image/object/truncated': dataset_util.int64_list_feature(truncated),
      'image/object/view': dataset_util.bytes_list_feature(poses),
  }))
  return example


def create_tf_record(output_filename,
                     label_map_dict,
                     annotations_dir,
                     image_dir,
                     examples):
  """Creates a TFRecord file from examples.

  Args:
    output_filename: Path to where output file is saved.
    label_map_dict: The label map dictionary.
    annotations_dir: Directory where annotation files are stored.
    image_dir: Directory where image files are stored.
    examples: Examples to parse and save to tf record.
  """
  writer = tf.python_io.TFRecordWriter(output_filename)
  for idx, example in enumerate(examples):
    if idx % 100 == 0:
      logging.info('On image %d of %d', idx, len(examples))
    path = os.path.join(annotations_dir, 'annos', example + '.xml')

    if not os.path.exists(path):
      logging.warning('Could not find %s, ignoring example.', path)
      continue
    with tf.gfile.GFile(path, 'r') as fid:
      xml_str = fid.read()
    xml = etree.fromstring(xml_str)
    data = dataset_util.recursive_parse_xml_to_dict(xml)['annotation']

    tf_example = dict_to_tf_example(data, label_map_dict, image_dir)
    writer.write(tf_example.SerializeToString())

  writer.close()


def main(_):
  label_map_dict = label_map_util.get_label_map_dict('D:/AI_SVT_Training_mk/annotations/label_map.pbtxt')
  logging.info('************************************Reading dataset.************************************')
  image_dir = 'D:/AI_SVT_Training_mk/annotations/annos'
  annotations_dir = 'D:/AI_SVT_Training_mk/annotations'
  examples_path = os.path.join(annotations_dir, 'train.txt')
  examples_list = dataset_util.read_examples_list(examples_path)

    
  # Test images are not included in the downloaded data set, so we shall perform
  # our own split.
  random.seed(42)
  random.shuffle(examples_list)
  num_examples = len(examples_list)

# JH: 배치파일에서 train set ratio 입력 받음
  #num_train = int(float(input('train_image_set 비율(0.0 ~ 1.0): ')) * num_examples)
  num_train = int(num_examples)
  print(f"**************Num_train:{num_train}**************")
  '''
  # mk:코드 정리 데이터셋부족해서 그냥 전부로햇음
  num_train = round(1 * num_examples)

  '''
  train_examples = examples_list[:num_train]
  val_examples = examples_list[num_train:]

  
  logging.info('%d training and %d validation examples.',
               len(train_examples), len(val_examples))

  train_output_path = 'train.record'
  val_output_path = 'val.record'
  create_tf_record(train_output_path, label_map_dict, annotations_dir,
                   image_dir, train_examples)
  create_tf_record(val_output_path, label_map_dict, annotations_dir,
                   image_dir, val_examples)
  print(f"*********************************It's make Record files Done*********************************")

if __name__ == '__main__':
  tf.app.run()
