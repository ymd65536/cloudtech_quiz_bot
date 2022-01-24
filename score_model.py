
import os
from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute,NumberAttribute

class Score(Model):
  class Meta:
    table_name = 'Score'
    region = 'ap-northeast-1'
    read_capacity_units = 1
    write_capacity_units = 1
    # aws_access_key_id = os.getenv('aws_access_key_id')
    # aws_secret_access_key = os.getenv('aws_secret_access_key')

  question_id = UnicodeAttribute(hash_key=True)
  question = UnicodeAttribute()
  answer = UnicodeAttribute()
  score = NumberAttribute()