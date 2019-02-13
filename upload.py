from __future__ import print_function
import pickle
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from apiclient.http import MediaFileUpload
from os import listdir
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
import json
import os.path
import argparse
import logging

scopes=['https://www.googleapis.com/auth/photoslibrary',
            'https://www.googleapis.com/auth/photoslibrary.sharing']

def parse_args(arg_input=None):
    parser = argparse.ArgumentParser(description='Upload photos to Google Photos.')
    parser.add_argument('--album', metavar='album_name', dest='album_name',
                    help='name of photo album to create (if it doesn\'t exist). Any uploaded photos will be added to this album.')
    parser.add_argument('photos', metavar='photo',type= str,
                    help='filename of a  folder of photo to upload')
    return parser.parse_args(arg_input)

def auth(scopes):
    cred= None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            cred = pickle.load(token)
    if not cred or not cred.valid:
        if cred and cred.expired and cred.refresh_token:
            cred.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
            'client_id.json',
            scopes=scopes)

            cred = flow.run_local_server(host='localhost',
                                        port=8080,
                                        authorization_prompt_message="",
                                        success_message='The auth flow is complete; you may close this window.',
                                        open_browser=True)
        with open('token.pickle', 'wb') as token:
            pickle.dump(cred, token)

    session = AuthorizedSession(cred)
    return session


def getAlbums(session, appCreatedOnly=False):

    params = {
            'excludeNonAppCreatedData': appCreatedOnly
    }

    while True:

        albums = session.get('https://photoslibrary.googleapis.com/v1/albums', params=params).json()

        logging.debug("Server response: {}".format(albums))

        if 'albums' in albums:

            for a in albums["albums"]:
                yield a

            if 'nextPageToken' in albums:
                params["pageToken"] = albums["nextPageToken"]
            else:
                return

        else:
            return

def create_or_retrieve_album(session, album_title):
# Find albums created by this app to see if one matches album_title
    for a in getAlbums(session, True):
        if a["title"].lower() == album_title.lower():
            album_id = a["id"]
            logging.info("Uploading into EXISTING photo album -- \'{0}\'".format(album_title))
            return album_id
# No matches, create new album
    create_album_body = json.dumps({"album":{"title": album_title}})
    print(create_album_body)
    resp = session.post('https://photoslibrary.googleapis.com/v1/albums', create_album_body).json()
    logging.debug("Server response: {}".format(resp))

    if "id" in resp:
        logging.info("Uploading into NEW photo album -- \'{0}\'".format(album_title))
        return resp['id']
    else:
        logging.error("Could not find or create photo album '\{0}\'. Server Response: {1}".format(album_title, resp))
        return None

def upload_photos(session, photo_file_list, album_name):
    album_id = create_or_retrieve_album(session, album_name) if album_name else None
    # interrupt upload if an upload was requested but could not be created
    if album_name and not album_id:
        return

    session.headers["Content-type"] = "application/octet-stream"
    session.headers["X-Goog-Upload-Protocol"] = "raw"

    print('photo_file_list',photo_file_list)
    dir1= str(photo_file_list)
    os.chdir(dir1)
    print(dir1)
    fnames= listdir(dir1)
    print(fnames)

    for fname in fnames:
            try:
                photo_file = open(fname, mode='rb')
                photo_bytes = photo_file.read()
            except OSError as err:
                logging.error("Could not read file \'{0}\' -- {1}".format(photo_file_name, err))
                continue

            session.headers["X-Goog-Upload-File-Name"] = os.path.basename(fname)

            logging.info("Uploading photo -- \'{}\'".format(fname))

            upload_token = session.post('https://photoslibrary.googleapis.com/v1/uploads', photo_bytes)

            if (upload_token.status_code == 200) and (upload_token.content):

                create_body = json.dumps({"albumId":album_id, "newMediaItems":[{"description":"","simpleMediaItem":{"uploadToken":upload_token.content.decode()}}]}, indent=4)

                resp = session.post('https://photoslibrary.googleapis.com/v1/mediaItems:batchCreate', create_body).json()

                logging.debug("Server response: {}".format(resp))

                if "newMediaItemResults" in resp:
                    status = resp["newMediaItemResults"][0]["status"]
                    if status.get("code") and (status.get("code") > 0):
                        logging.error("Could not add \'{0}\' to library -- {1}".format(os.path.basename(fname), status["message"]))
                    else:
                        logging.info("Added \'{}\' to library and album \'{}\' ".format(os.path.basename(fname), album_name))
                else:
                    logging.error("Could not add \'{0}\' to library. Server Response -- {1}".format(os.path.basename(fname), resp))
            else:
                logging.error("Could not upload \'{0}\'. Server Response - {1}".format(os.path.basename(fname), upload_token))

    try:
        del(session.headers["Content-type"])
        del(session.headers["X-Goog-Upload-Protocol"])
        del(session.headers["X-Goog-Upload-File-Name"])
    except KeyError:
        pass

def main():
    args = parse_args()
    session = auth(scopes)
    upload_photos(session, args.photos, args.album_name)

    print("{:<50} | {:>8} | {} ".format("PHOTO ALBUM","# PHOTOS", "IS WRITEABLE?"))

    for a in getAlbums(session):
        print("{:<50} | {:>8} | {} ".format(a["title"],a.get("mediaItemsCount", "0"), str(a.get("isWriteable", False))))

if __name__ == '__main__':
  main()
