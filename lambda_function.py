import os
import json
import requests
import boto3

from linebot import LineBotApi
from linebot.models import TextSendMessage, FlexSendMessage

from pynamodb.models import Model
from pynamodb.attributes import UnicodeAttribute, NumberAttribute, MapAttribute

# アクセストークン
access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

# bot のユーザID
bot_user_id = os.getenv('LINE_USER_ID')
line_bot = LineBotApi(access_token)

# 問題毎のユーザスコアを格納するクラス
# UserScore モデルから参照
class ScoreMap(MapAttribute):
  q1 = NumberAttribute(null=True)
  q2 = NumberAttribute(null=True)
  q3 = NumberAttribute(null=True)

dynamodb = boto3.resource('dynamodb')
scores = dynamodb.Table('Score')

# ユーザスコアを格納するモデル
class UserScore(Model):
  class Meta:
    table_name = 'UserScore'
    region = 'ap-northeast-1'
    # aws_access_key_id = os.getenv('aws_access_key_id')
    # aws_secret_access_key = os.getenv('aws_secret_access_key')
  line_user_id = UnicodeAttribute(hash_key=True)
  scores = MapAttribute(of=ScoreMap)

def get_result(question, answer):
    question_info = scores.get_item(Key={"question_id": question})['Item']
    score = 0
    if question_info['answer'] == answer:
        score = int(question_info['score'])
    return score

def get_next_question(inserted_question):
    if inserted_question == 'q1':
        next_question = scores.get_item(
            Key={"question_id": 'q2'}
        )['Item']['question']
    elif inserted_question == 'q2':
        next_question = scores.get_item(
            Key={"question_id": 'q3'}
        )['Item']['question']
    return FlexSendMessage(
        alt_text='Next Question',
        contents=json.loads(next_question)
    )

def update_score(user_score, answer):
    # 各設問に対するスコアを挿入する
    inserted_question = ''
    if user_score.scores['q1'] is None:
        score = get_result('q1', answer)
        inserted_question = 'q1'
    elif user_score.scores['q2'] is None:
        score = get_result('q2', answer)
        inserted_question = 'q2'
    elif user_score.scores['q3'] is None:
        score = get_result('q3', answer)
        inserted_question = 'q3'

    # スコアを更新する
    if inserted_question != '':
        user_score.scores[inserted_question] = score
        user_score.save()

    if score == 0:
        result_msg = TextSendMessage(text='不正解です')
    else:
        result_msg = TextSendMessage(text='正解です')

    # 最終問題であれば結果を返す
    if inserted_question == 'q3':
        result_data = UserScore.get(user_score.line_user_id)
        total_score = result_data.scores['q1'] + \
            result_data.scores['q2'] + result_data.scores['q3']
        next_msg = TextSendMessage(
            text='以上で問題は終了です\n合計得点は{}点です'.format(total_score))
    else:
        next_msg = get_next_question(inserted_question)

    # 次の設問を返す
    return {
        'inserted_question': inserted_question,
        'score': score,
        'msg': [result_msg, next_msg]
    }

# リッチメニューを設定する関数
def register_and_apply_richmenu():
    print('register richmenu')

    # チャネルアクセストークンの設定
    # ベアラー
    headers = {"Authorization": "Bearer {%s}" % access_token}

    # リッチメニューの名前を設定
    rich_menu_name = "start_menu"

    # チャットバーのテキスト
    chat_bar_name = "メニューを開く"

    # 範囲は画像と同じ大きさに設定
    x = 0
    y = 0
    width = 2500
    height = 843
    bounds={"x":x,"y":y,"width":width,"height":height}

    # 画像サイズの指定
    size = {"width":width, "height": height}

    # リッチメニューのアクションタイプ
    action = {"type": "message"}
    action["text"] = "start"
    areas = []
    areas.append({"bounds": bounds, "action": action})

    # 画像パス
    image_path= "./img/menu.png"

    # 送信データの作成
    send_dic = {"size":size,"selected":True,"name":rich_menu_name,"chatBarText":chat_bar_name,"areas":areas}
    send_json = json.dumps(send_dic)

    # リッチメニューの登録
    register_url = "https://api.line.me/v2/bot/richmenu"
    res = requests.post(register_url, headers=dict(headers, **{"Content-Type": "application/json"}), data=send_json,verify=True).json()
    rich_menu_id = res["richMenuId"]

    # 取得したリッチメニューIDを元に画像をアップロード
    upload_url = "https://api-data.line.me/v2/bot/richmenu/%s/content" % rich_menu_id
    image_file = open(image_path,"rb")
    requests.post(upload_url, headers=dict(headers, **{"Content-Type": "image/jpeg"}), data=image_file, verify=True)

    # 特定のユーザIDにリッチメニューを登録
    apply_url = "https://api.line.me/v2/bot/user/%s/richmenu/%s" % (bot_user_id,rich_menu_id)
    requests.post(apply_url, headers=headers, verify=True)

    # リッチメニューの設定をチェック
    applied_url = "https://api.line.me/v2/bot/user/%s/richmenu" % bot_user_id
    res = requests.get(applied_url, headers=headers, verify=True).json()

    if not res["richMenuId"] == "":
        print("リッチメニューが設定されています。")

def lambda_handler(event, context):

  print("Received event: " + json.dumps(event, indent=2))

  # Webhookの接続確認用
  body = json.loads(event['body'])

  if len(body['events']) == 0:
      return {
          'statusCode': 200,
          'body': ''
      }

  print(body)
  user_id = body['events'][0]['source']['userId']

  event_type = body['events'][0]['type']
  message_text = body['events'][0]['message']['text'] if event_type == 'message' else ''

  if event_type == 'follow' :
    # アカウントがフォローされたときはリッチメニューを適用する
    register_and_apply_richmenu()

  elif message_text == 'start' :

    #「start」が入力された時に出題開始
    reply_token =  body['events'][0]['replyToken']
    # ユーザスコアが存在しない場合は作成する
    # iam:dynamodb:DescribeTable
    if not UserScore.exists():
      UserScore.create_table(read_capacity_units=1,
                            write_capacity_units=1, wait=True)

    # ユーザIDが存在しない場合は登録する
    UserScore(
                line_user_id=user_id,
                scores=ScoreMap(q1=None, q2=None, q3=None)
            ).save()
    
    # 最初の問題を取り出す
    first_question = scores.get_item(
                Key={"question_id": 'q1'}
            )['Item']['question']

    # クイズ開始のメッセージ
    greet_msg = "AWSにまつわる問題を用意しました。クイズを開始します。"
    print(greet_msg)

    greet_msg = TextSendMessage(
      text=greet_msg
    )

    # リプライトークンでFlexMessageを返信
    question_msg = FlexSendMessage(
        alt_text='First Question',
        contents=json.loads(first_question)
    )
    line_bot.reply_message(
        reply_token,
        [greet_msg, question_msg]
    )
    return {
        'statusCode': 200,
        'body': json.dumps('Init Success!')
    }
  elif event_type == 'unfollow':
      # ブロックされた時にはデータを削除する
      UserScore.get(user_id).delete()
      return {
          'statusCode': 200,
          'body': json.dumps('Delete Success!')
      }
  else:

    reply_token =  body['events'][0]['replyToken']
    # 2問目以降
    user_score = UserScore.get(user_id)

    # 入力チェック
    if message_text.isnumeric():

      # 問題に対するスコアを取得
      # ユーザスコアを更新
      # 正解 or 不正解を 返す
      result = update_score(user_score, message_text)

      print('Question: {}\nScore: {}'.format(
      result['inserted_question'], result['score']))
      
      msg_obj = result['msg']

      line_bot.reply_message(
          reply_token,
          msg_obj
      )

    else:
      print("数値を入力してください。")