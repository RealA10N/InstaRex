from __future__ import unicode_literals

import imghdr
import os
import shutil
import struct
import json
import time
import random
from uuid import uuid4

from PIL import Image, ExifTags
from math import ceil

from . import config


def download_photo(self, media_id, filename, media=False, folder="photos"):
    if not media:
        self.media_info(media_id)
        if not self.last_json.get("items"):
            return True
        media = self.last_json["items"][0]
    if media["media_type"] == 2:
        return True
    elif media["media_type"] == 1:
        filename = (
            "{username}_{media_id}.jpg".format(
                username=media["user"]["username"], media_id=media_id
            )
            if not filename
            else "{fname}.jpg".format(fname=filename)
        )
        images = media["image_versions2"]["candidates"]
        fname = os.path.join(folder, filename)
        if os.path.exists(fname):
            self.logger.info("File already esists, skipping...")
            return os.path.abspath(fname)
        response = self.session.get(images[0]["url"], stream=True)
        if response.status_code == 200:
            with open(fname, "wb") as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)
            return os.path.abspath(fname)
    else:
        success = False
        video_included = False
        for index in range(len(media["carousel_media"])):
            if media["carousel_media"][index]["media_type"] != 1:
                video_included = True
                continue
            filename_i = (
                "{username}_{media_id}_{i}.jpg".format(
                    username=media["user"]["username"], media_id=media_id, i=index
                )
                if not filename
                else "{fname}_{i}.jpg".format(fname=filename, i=index)
            )
            images = media["carousel_media"][index]["image_versions2"]["candidates"]
            fname = os.path.join(folder, filename_i)
            if os.path.exists(fname):
                return os.path.abspath(fname)
            response = self.session.get(images[0]["url"], stream=True)
            if response.status_code == 200:
                success = True
                with open(fname, "wb") as f:
                    response.raw.decode_content = True
                    shutil.copyfileobj(response.raw, f)
        if success:
            return os.path.abspath(fname)
        elif video_included:
            return True


def compatible_aspect_ratio(size):
    min_ratio, max_ratio = 4.0 / 5.0, 90.0 / 47.0
    width, height = size
    ratio = width * 1.0 / height * 1.0
    print("FOUND: w:{w} h:{h} r:{r}".format(w=width, h=height, r=ratio))
    return min_ratio <= ratio <= max_ratio


def configure_photo(self, upload_id, photo_size, caption="", user_tags=None, is_sidecar=False):
    width, height = photo_size
    data = {
            "media_folder": "Instagram",
            "source_type": 4,
            "caption": caption,
            "upload_id": upload_id,
            "device": self.device_settings,
            "edits": {
                "crop_original_size": [width * 1.0, height * 1.0],
                "crop_center": [0.0, 0.0],
                "crop_zoom": 1.0,
            },
            "extra": {"source_width": width, "source_height": height},
        }
    if user_tags:
        data['usertags'] = user_tags

    if is_sidecar:
        return data

    data = self.json_data(data)
    return self.send_request("media/configure/?", data)


def upload_photo(
    self,
    photo,
    caption=None,
    upload_id=None,
    from_video=False,
    force_resize=False,
    options={},
    user_tags=None,
    is_sidecar=False
):
    """Upload photo to Instagram

    @param photo         Path to photo file (String)
    @param caption       Media description (String)
    @param upload_id     Unique upload_id (String). When None, then generate
                         automatically
    @param from_video    A flag that signals whether the photo is loaded from
                         the video or by itself
                         (Boolean, DEPRECATED: not used)
    @param force_resize  Force photo resize (Boolean)
    @param options       Object with difference options, e.g.
                         configure_timeout, rename (Dict)
                         Designed to reduce the number of function arguments!
                         This is the simplest request object.
    @param user_tags     Tag other users (List)
                         usertags = [
                            {"user_id": user_id, "position": [x, y]}
                         ]
    @param is_sidecar    An album element (Boolean)

    @return Object with state of uploading to Instagram (or False), Dict for is_sidecar
    """
    if user_tags is None:
        usertags = None
    else:
        tags = {'in': [{'user_id': user['user_id'], 'position': [user['x'], user['y']]} for user in user_tags]}
        usertags = json.dumps(tags, separators=(',', ':'))

    options = dict({"configure_timeout": 15, "rename": True}, **(options or {}))
    if upload_id is None:
        upload_id = int(time.time() * 1000)
    if not photo:
        return False
    if not compatible_aspect_ratio(photo.size):
        self.logger.error("Photo does not have a compatible photo aspect ratio.")
        if force_resize:
            photo = resize_image(photo)
        else:
            return False
    waterfall_id = str(uuid4())
    # upload_name example: '1576102477530_0_7823256191'
    # upload_name example:  'fb_uploader_1585807380927'
    upload_name = "fb_uploader_{upload_id}".format(upload_id=upload_id)
    rupload_params = {
        "retry_context": '{"num_step_auto_retry":0,"num_reupload":0,"num_step_manual_retry":0}',
        "media_type": "1",
        "xsharing_user_ids": "[]",
        "upload_id": upload_id,
        "image_compression": json.dumps(
            {"lib_name": "moz", "lib_version": "3.1.m", "quality": "80"}
        ),
    }
    if is_sidecar:
        rupload_params["is_sidecar"] = "1"
    photo_data = open(photo, "rb").read()
    photo_len = str(len(photo_data))
    self.session.headers.update(
        {
            "Accept-Encoding": "gzip",
            "X-Instagram-Rupload-Params": json.dumps(rupload_params),
            "X_FB_PHOTO_WATERFALL_ID": waterfall_id,
            "X-Entity-Type": "image/jpeg",
            "Offset": "0",
            "X-Entity-Name": upload_name,
            "X-Entity-Length": photo_len,
            "Content-Type": "application/octet-stream",
            "Content-Length": photo_len,
            "Accept-Encoding": "gzip",
        }
    )
    response = self.session.post(
        "https://{domain}/rupload_igphoto/{name}".format(
            domain=config.API_DOMAIN, name=upload_name
        ),
        data=photo_data,
    )

    if response.status_code != 200:
        self.logger.error(
            "Photo Upload failed with the following response: {}".format(response)
        )
        return False
    # update the upload id
    upload_id = int(response.json()['upload_id'])
    if from_video:
        # Not configure when from_video is True
        return True
    # CONFIGURE
    configure_timeout = options.get("configure_timeout")
    for attempt in range(4):
        if configure_timeout:
            time.sleep(configure_timeout)
        if is_sidecar:
            configuration = self.configure_photo(upload_id, photo.size, caption, usertags, is_sidecar=True)
            if options.get("rename"):
                os.rename(photo, "{fname}.REMOVE_ME".format(fname=photo))
            return configuration
        elif self.configure_photo(upload_id, photo.size, caption, usertags, is_sidecar=False):
            media = self.last_json.get("media")
            self.expose()
            if options.get("rename"):
                os.rename(photo, "{fname}.REMOVE_ME".format(fname=photo))
            return media
    return False


def upload_album(
    self,
    photos,
    caption=None,
    upload_id=None,
    from_video=False,
    force_resize=False,
    options={},
    user_tags=None
):
    """Upload album to Instagram

    @param photos        List of paths to photo files (List of strings)
    @param caption       Media description (String)
    @param upload_id     Unique upload_id (String). When None, then generate
                         automatically
    @param from_video    A flag that signals whether the photo is loaded from
                         the video or by itself
                         (Boolean, DEPRECATED: not used)
    @param force_resize  Force photo resize (Boolean)
    @param options       Object with difference options, e.g.
                         configure_timeout, rename (Dict)
                         Designed to reduce the number of function arguments!
                         This is the simplest request object.
    @param user_tags

    @return Boolean
    """
    if not photos:
        return False
    photo_metas = []
    for photo in photos:
        result = self.upload_photo(photo, caption, None, from_video, force_resize, options, user_tags, is_sidecar=True)
        if not result:
            self.logger.error("Could not upload photo {photo} for the album!".format(photo=photo))
            return False
        photo_metas.append(result)
    if upload_id is None:
        upload_id = int(time.time() * 1000)
    data = self.json_data({
        "caption": caption,
        "client_sidecar_id": upload_id,
        "children_metadata": photo_metas
    })
    return self.send_request("media/configure_sidecar/?", post=data)


def resize_image(img):
    """ Recives a PIL image object, and returns another PIL resized image
    object - to match Instagram's post sizes. """

    h_lim = {"w": 90.0, "h": 47.0}
    v_lim = {"w": 4.0, "h": 5.0}
    (w, h) = img.size
    deg = 0

    try:
        for orientation in ExifTags.TAGS.keys():
            if ExifTags.TAGS[orientation] == "Orientation":
                break
        exif = dict(img._getexif().items())
        o = exif[orientation]
        if o == 3:
            deg = 180
        if o == 6:
            deg = 270
        if o == 8:
            deg = 90
        if deg != 0:
            print("Rotating by {d} degrees".format(d=deg))
            img = img.rotate(deg, expand=True)
            (w, h) = img.size

    except (AttributeError, KeyError, IndexError) as e:
        print("No exif info found (ERR: {err})".format(err=e))

    img = img.convert("RGBA")
    ratio = w * 1.0 / h * 1.0
    print("FOUND w:{w}, h:{h}, ratio={r}".format(w=w, h=h, r=ratio))

    if w > h:
        print("Horizontal image")
        if ratio > (h_lim["w"] / h_lim["h"]):
            print("Cropping image")
            cut = int(ceil((w - h * h_lim["w"] / h_lim["h"]) / 2))
            left = cut
            right = w - cut
            top = 0
            bottom = h
            img = img.crop((left, top, right, bottom))
            (w, h) = img.size
        if w > 1080:
            print("Resizing image")
            nw = 1080
            nh = int(ceil(1080.0 * h / w))
            img = img.resize((nw, nh), Image.ANTIALIAS)

    elif w < h:
        print("Vertical image")
        if ratio < (v_lim["w"] / v_lim["h"]):
            print("Cropping image")
            cut = int(ceil((h - w * v_lim["h"] / v_lim["w"]) / 2))
            left = 0
            right = w
            top = cut
            bottom = h - cut
            img = img.crop((left, top, right, bottom))
            (w, h) = img.size
        if h > 1080:
            print("Resizing image")
            nw = int(ceil(1080.0 * w / h))
            nh = 1080
            img = img.resize((nw, nh), Image.ANTIALIAS)

    else:
        print("Square image")
        if w > 1080:
            print("Resizing image")
            img = img.resize((1080, 1080), Image.ANTIALIAS)

    (w, h) = img.size
    new = Image.new("RGB", img.size, (255, 255, 255))
    new.paste(img, (0, 0, w, h), img)
    return new


def stories_shaper(fname):
    """
    Find out the size of the uploaded image. Processing is not needed if the
    image is already 1080x1920 pixels. Otherwise, the image height should be
    1920 pixels. Substrate formation: Crop the image under 1080x1920 pixels
    and apply a Gaussian Blur filter. Centering the image depending on its
    aspect ratio and paste it onto the substrate. Save the image.
    """
    try:
        from PIL import Image, ImageFilter
    except ImportError as e:
        print("ERROR: {err}".format(err=e))
        print(
            "Required module `PIL` not installed\n"
            "Install with `pip install Pillow` and retry"
        )
        return False
    img = Image.open(fname)
    if (img.size[0], img.size[1]) == (1080, 1920):
        print("Image is already 1080x1920. Just converting image.")
        new_fname = "{fname}.STORIES.jpg".format(fname=fname)
        new = Image.new("RGB", (img.size[0], img.size[1]), (255, 255, 255))
        new.paste(img, (0, 0, img.size[0], img.size[1]))
        new.save(new_fname)
        return new_fname
    else:
        min_width = 1080
        min_height = 1920
        if img.size[1] != 1920:
            height_percent = min_height / float(img.size[1])
            width_size = int(float(img.size[0]) * float(height_percent))
            img = img.resize((width_size, min_height), Image.ANTIALIAS)
        else:
            pass
        if img.size[0] < 1080:
            width_percent = min_width / float(img.size[0])
            height_size = int(float(img.size[1]) * float(width_percent))
            img_bg = img.resize((min_width, height_size), Image.ANTIALIAS)
        else:
            pass
        img_bg = img.crop(
            (
                int((img.size[0] - 1080) / 2),
                int((img.size[1] - 1920) / 2),
                int(1080 + ((img.size[0] - 1080) / 2)),
                int(1920 + ((img.size[1] - 1920) / 2)),
            )
        ).filter(ImageFilter.GaussianBlur(100))
        if img.size[1] > img.size[0]:
            height_percent = min_height / float(img.size[1])
            width_size = int(float(img.size[0]) * float(height_percent))
            img = img.resize((width_size, min_height), Image.ANTIALIAS)
            if img.size[0] > 1080:
                width_percent = min_width / float(img.size[0])
                height_size = int(float(img.size[1]) * float(width_percent))
                img = img.resize((min_width, height_size), Image.ANTIALIAS)
                img_bg.paste(
                    img, (int(540 - img.size[0] / 2), int(960 - img.size[1] / 2))
                )
            else:
                img_bg.paste(img, (int(540 - img.size[0] / 2), 0))
        else:
            width_percent = min_width / float(img.size[0])
            height_size = int(float(img.size[1]) * float(width_percent))
            img = img.resize((min_width, height_size), Image.ANTIALIAS)
            img_bg.paste(img, (int(540 - img.size[0] / 2), int(960 - img.size[1] / 2)))
        new_fname = "{fname}.STORIES.jpg".format(fname=fname)
        print(
            "Saving new image w:{w} h:{h} to `{f}`".format(
                w=img_bg.size[0], h=img_bg.size[1], f=new_fname
            )
        )
        new = Image.new("RGB", (img_bg.size[0], img_bg.size[1]), (255, 255, 255))
        new.paste(img_bg, (0, 0, img_bg.size[0], img_bg.size[1]))
        new.save(new_fname)
        return new_fname
