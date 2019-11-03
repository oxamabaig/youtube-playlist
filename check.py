# -*- coding: utf-8 -*-

import os
import flask
import requests
import json
import csv
from flask import Flask, render_template, jsonify, request, redirect, url_for
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery
import pandas
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# This variable specifies the name of a file that contains the OAuth 2.0
# information for this application, including its client_id and client_secret.
CLIENT_SECRETS_FILE = "client2.json"

# This OAuth 2.0 access scope allows for full read/write access to the
# authenticated user's account and requires requests to use an SSL connection.
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

app = flask.Flask(__name__)
# Note: A secret key is included in the sample so that it works.
# If you use this code in your application, replace this with a truly secret
# key. See http://flask.pocoo.org/docs/0.12/quickstart/#sessions.
app.secret_key = '!\xa1\xf3P\x13\xc1\xd2y\xafO*\x1a>\xb2\xa6C\xbd\x8a\xe7"\xaf\x95\xbd\xd4'


@app.route('/')
def index():
    Message = 'hide'
    return render_template("index.html", message = Message)


@app.route('/setParameters', methods={'GET','POST'})
def setParametrs():
    if(request.method == 'POST'):
        searchItem = request.form.get('searchItem')
        maxResults = request.form.get('maxResults')
        playlistTitle = request.form.get('playlistTitle')
        playlistDescription = request.form.get('playlistDescription')
        privacy = request.form.get('privacy')
        front_video_id = request.form.get('front_video_id')        
        with open('parameters.csv', mode='w') as csv_file:
            fieldnames = ['searchItem', 'maxResults', 'playlistTitle', 'playlistDescription', 'playlistPrivacy', 'front_video_id']
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({'searchItem': searchItem, 'maxResults': maxResults, 'playlistTitle': playlistTitle, 'playlistDescription': playlistDescription, 'playlistPrivacy': privacy, 'front_video_id': front_video_id})        
    print("Set Parametrs!")
    Message = 'show'
    return render_template("index.html", message = Message)

@app.route('/test')
def test_api_request():
  if 'credentials' not in flask.session:
    return flask.redirect('authorize')

  # Load credentials from the session.
  credentials = google.oauth2.credentials.Credentials(
      **flask.session['credentials'])

  youtube = googleapiclient.discovery.build(
      API_SERVICE_NAME, API_VERSION, credentials=credentials)

  df = pandas.read_csv('parameters.csv')  
  search_response = youtube.search().list(
    q=df['searchItem'][0],
    part="snippet",
    maxResults=df['maxResults'][0]
  ).execute()        
  temp = json.loads(json.dumps(search_response))
  with open('videos.csv', mode='w') as csv_file:
          fieldnames = ['kind', 'videoId']
          writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
          writer.writeheader()
          for item in  temp['items']:
            #print(item['id']['kind'])
            #print(item['id']['videoId'])
            writer.writerow({'kind': item['id']['kind'], 'videoId': item['id']['videoId']})
  playlists_insert_response = youtube.playlists().insert(
    part="snippet,status",
    body=dict(
      snippet=dict(
        title=df['playlistTitle'][0],
        description=df['playlistDescription'][0]
      ),
      status=dict(
        privacyStatus=df['playlistPrivacy'][0]
      )
    )
  ).execute()
  playlistID = playlists_insert_response["id"]
  dp = pandas.read_csv('videos.csv')
  add_video_request=youtube.playlistItems().insert(
  part="snippet",
  body={
        'snippet': {
          'playlistId': playlistID, 
          'resourceId': {
                  'kind': 'youtube#video',
              'videoId': df['front_video_id'][0]
            }
        #'position': 0
        }
  }
  ).execute()
  for video in dp['videoId']:
        add_video_request=youtube.playlistItems().insert(
        part="snippet",
        body={
                'snippet': {
                'playlistId': playlistID, 
                'resourceId': {
                        'kind': 'youtube#video',
                    'videoId': video
                    }
                #'position': 0
                }
        }
        ).execute()
  # Save credentials back to session in case access token was refreshed.
  # ACTION ITEM: In a production app, you likely want to save these
  #              credentials in a persistent database instead.
  flask.session['credentials'] = credentials_to_dict(credentials)
  return render_template("index.html")


@app.route('/authorize')
def authorize():
  # Create flow instance to manage the OAuth 2.0 Authorization Grant Flow steps.
  flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
      CLIENT_SECRETS_FILE, scopes=SCOPES)

  # The URI created here must exactly match one of the authorized redirect URIs
  # for the OAuth 2.0 client, which you configured in the API Console. If this
  # value doesn't match an authorized URI, you will get a 'redirect_uri_mismatch'
  # error.
  flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

  authorization_url, state = flow.authorization_url(
      # Enable offline access so that you can refresh an access token without
      # re-prompting the user for permission. Recommended for web server apps.
      access_type='offline',
      # Enable incremental authorization. Recommended as a best practice.
      include_granted_scopes='true')

  # Store the state so the callback can verify the auth server response.
  flask.session['state'] = state

  return flask.redirect(authorization_url)


@app.route('/oauth2callback')
def oauth2callback():
  # Specify the state when creating the flow in the callback so that it can
  # verified in the authorization server response.
  state = flask.session['state']

  flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
      CLIENT_SECRETS_FILE, scopes=SCOPES, state=state)
  flow.redirect_uri = flask.url_for('oauth2callback', _external=True)

  # Use the authorization server's response to fetch the OAuth 2.0 tokens.
  authorization_response = flask.request.url
  flow.fetch_token(authorization_response=authorization_response)

  # Store credentials in the session.
  # ACTION ITEM: In a production app, you likely want to save these
  #              credentials in a persistent database instead.
  credentials = flow.credentials
  flask.session['credentials'] = credentials_to_dict(credentials)

  return flask.redirect(flask.url_for('test_api_request'))


@app.route('/revoke')
def revoke():
  if 'credentials' not in flask.session:
    return ('You need to <a href="/authorize">authorize</a> before ' +
            'testing the code to revoke credentials.')

  credentials = google.oauth2.credentials.Credentials(
    **flask.session['credentials'])

  revoke = requests.post('https://accounts.google.com/o/oauth2/revoke',
      params={'token': credentials.token},
      headers = {'content-type': 'application/x-www-form-urlencoded'})

  status_code = getattr(revoke, 'status_code')
  if status_code == 200:
    return('Credentials successfully revoked.' + print_index_table())
  else:
    return('An error occurred.' + print_index_table())


@app.route('/clear')
def clear_credentials():
  if 'credentials' in flask.session:
    del flask.session['credentials']
  return ('Credentials have been cleared.<br><br>' +
          print_index_table())


def credentials_to_dict(credentials):
  return {'token': credentials.token,
          'refresh_token': credentials.refresh_token,
          'token_uri': credentials.token_uri,
          'client_id': credentials.client_id,
          'client_secret': credentials.client_secret,
          'scopes': credentials.scopes}

def print_index_table():
  return ('<table>' +
          '<tr><td><a href="/test">Test an API request</a></td>' +
          '<td>Submit an API request and see a formatted JSON response. ' +
          '    Go through the authorization flow if there are no stored ' +
          '    credentials for the user.</td></tr>' +
          '<tr><td><a href="/authorize">Test the auth flow directly</a></td>' +
          '<td>Go directly to the authorization flow. If there are stored ' +
          '    credentials, you still might not be prompted to reauthorize ' +
          '    the application.</td></tr>' +
          '<tr><td><a href="/revoke">Revoke current credentials</a></td>' +
          '<td>Revoke the access token associated with the current user ' +
          '    session. After revoking credentials, if you go to the test ' +
          '    page, you should see an <code>invalid_grant</code> error.' +
          '</td></tr>' +
          '<tr><td><a href="/clear">Clear Flask session credentials</a></td>' +
          '<td>Clear the access token currently stored in the user session. ' +
          '    After clearing the token, if you <a href="/test">test the ' +
          '    API request</a> again, you should go back to the auth flow.' +
          '</td></tr></table>')


if __name__ == '__main__':
  # When running locally, disable OAuthlib's HTTPs verification.
  # ACTION ITEM for developers:
  #     When running in production *do not* leave this option enabled.
  os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

  # Specify a hostname and port that are set as a valid redirect URI
  # for your API project in the Google API Console.
  app.run('localhost', 5000, debug=True)