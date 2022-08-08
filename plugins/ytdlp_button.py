import asyncio
import json
import os
from logging import getLogger, WARNING
from os import remove as osremove, walk, path as ospath, rename as osrename
from time import time, sleep
from pyrogram.errors import FloodWait, RPCError
from PIL import Image
from threading import RLock
from pyrogram.types import Message
import shutil
import time
from datetime import datetime

from config import DOWNLOAD_LOCATION, LOG_CHANNEL, HTTP_PROXY, TG_MAX_FILE_SIZE, DEF_WATER_MARK_FILE, PROMO, PRE_LOG, userbot, BOT_PM, OWNER_ID

from pyrogram.enums import MessageEntityType, ChatAction
from database.database import db
from translation import Translation

from pyrogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, MessageNotModified
from functions.progress import progress_for_pyrogram, humanbytes
from functions.ffmpeg import generate_screen_shots, VideoThumb, VideoMetaData, VMMetaData, DocumentThumb, \
    AudioMetaData
from functions.utils import remove_urls, remove_emoji

import logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler('log.txt'), logging.StreamHandler()],
                    level=logging.INFO)
LOGGER = logging.getLogger(__name__)

class Urlyukle:
    def __init__(self, name=None, listener=None):
        self.name = name
        self.uploaded_bytes = 0
        self._last_uploaded = 0
        self.__listener = listener
        self.__start_time = time()
        self.__total_files = 0
        self.__is_cancelled = False
        self.__as_doc = AS_DOCUMENT
        self.__thumb = f"Thumbnails/{listener.message.from_user.id}.jpg"
        self.__msgs_dict = {}
        self.__corrupted = 0
        self.__resource_lock = RLock()
        self.__is_corrupted = False
        self.__sent_msg = bot.get_messages(self.__listener.message.chat.id, self.__listener.uid)
        self.__user_settings()
        self.__leech_log = PRE_LOG.copy()  # copy then pop to keep the original var as it is
        self.__bot = bot
        self.__user_id = listener.message.from_user.id
        self.isPrivate = listener.message.chat.type in ['private', 'group'] 

async def yt_dlp_call_back(bot, update):
    cb_data = update.data
    tg_send_type, yt_dlp_format, yt_dlp_ext, random = cb_data.split("|")

    dtime = str(time.time())
    
    message = update.message
    current_user_id = message.reply_to_message.from_user.id
    user_id = update.from_user.id
    chat_id = message.chat.id
    message_id = message.id
    
    if current_user_id != user_id:
        await bot.answer_callback_query(
            callback_query_id=update.id,
            text="Seni tanımıyorum ahbap.",
            show_alert=True,
            cache_time=0,
        )
        return False, None

    thumb_image_path = DOWNLOAD_LOCATION + \
                       "/" + str(user_id) + f'{random}' + ".jpg"
    save_ytdl_json_path = DOWNLOAD_LOCATION + \
                          "/" + str(user_id) + f'{random}' + ".json"
    LOGGER.info(save_ytdl_json_path)

    try:
        with open(save_ytdl_json_path, "r", encoding="utf8") as f:
            response_json = json.load(f)
    except FileNotFoundError as e:
        await bot.delete_messages(
            chat_id=chat_id,
            message_ids=message_id,
            revoke=True
        )
        return False
    #
    response_json = response_json[0]
    # TODO: temporary limitations
    # LOGGER.info(response_json)

    yt_dlp_url = message.reply_to_message.text

    name = str(response_json.get("title")[:100]) + \
           "." + yt_dlp_ext

    custom_file_name = remove_emoji(remove_urls(name))
    LOGGER.info(name)
    #
    yt_dlp_username = None
    yt_dlp_password = None
    if "|" in yt_dlp_url:
        url_parts = yt_dlp_url.split("|")
        if len(url_parts) == 2:
            yt_dlp_url = url_parts[0]
            custom_file_name = url_parts[1]
            caption = custom_file_name
            if len(custom_file_name) > 60:
                await update.edit_message_text(
                    Translation.IFLONG_FILE_NAME.format(
                        alimit="64",
                        num=len(custom_file_name)
                    )
                )
                return
        elif len(url_parts) == 4:
            yt_dlp_url = url_parts[0]
            custom_file_name = url_parts[1]
            yt_dlp_username = url_parts[2]
            yt_dlp_password = url_parts[3]
        else:
            for entity in message.reply_to_message.entities:
                if entity.type == MessageEntityType.TEXT_LINK:
                    yt_dlp_url = entity.url
                elif entity.type == MessageEntityType.URL:
                    o = entity.offset
                    l = entity.length
                    yt_dlp_url = yt_dlp_url[o:o + l]
        if yt_dlp_url is not None:
            yt_dlp_url = yt_dlp_url.strip()
        if custom_file_name is not None:
            custom_file_name = custom_file_name.strip()
        if yt_dlp_username is not None:
            yt_dlp_username = yt_dlp_username.strip()
        if yt_dlp_password is not None:
            yt_dlp_password = yt_dlp_password.strip()
        LOGGER.info(yt_dlp_url)
        LOGGER.info(custom_file_name)
    else:
        if "fulltitle" in response_json:
            title = response_json["fulltitle"][0:100]
            if (await db.get_caption(user_id)) is True:
                if "description" in response_json:
                    description = response_json["description"][0:821]
                    caption = title + "\n\n" + description
                else:
                    caption = title
            else:
                caption = title
        for entity in message.reply_to_message.entities:
            if entity.type == MessageEntityType.TEXT_LINK:
                yt_dlp_url = entity.url
            elif entity.type == MessageEntityType.URL:
                o = entity.offset
                l = entity.length
                yt_dlp_url = yt_dlp_url[o:o + l]

    await bot.edit_message_text(
        text=Translation.DOWNLOAD_START.format(custom_file_name),
        chat_id=chat_id,
        message_id=message_id
    )

    tmp_directory_for_each_user = os.path.join(
        DOWNLOAD_LOCATION,
        str(user_id),
        dtime
    )
    if not os.path.isdir(tmp_directory_for_each_user):
        os.makedirs(tmp_directory_for_each_user)
    download_directory = os.path.join(tmp_directory_for_each_user, custom_file_name)
    command_to_exec = []
    if tg_send_type == "audio":
        command_to_exec = [
            "yt-dlp",
            "-c",
            "--max-filesize", str(TG_MAX_FILE_SIZE),
            "--prefer-ffmpeg",
            "--extract-audio",
            "--audio-format", yt_dlp_ext,
            "--audio-quality", yt_dlp_format,
            yt_dlp_url,
            "-o", download_directory
        ]
    else:
        try:
            for for_mat in response_json["formats"]:
                format_id = for_mat.get("format_id")
                if format_id == yt_dlp_format:
                    acodec = for_mat.get("acodec")
                    if acodec == "none":
                        yt_dlp_format += "+bestaudio"
                    break

            command_to_exec = [
                "yt-dlp",
                "-c",
                "--max-filesize", str(TG_MAX_FILE_SIZE),
                "--embed-subs",
                "-f", yt_dlp_format,
                "--hls-prefer-ffmpeg", yt_dlp_url,
                "-o", download_directory
            ]
        except KeyError:
            command_to_exec = [
                "yt-dlp",
                "-c",
                "--max-filesize", str(TG_MAX_FILE_SIZE),
                yt_dlp_url, "-o", download_directory
            ]

    if await db.get_aria2(user_id) is True:
        command_to_exec.append("--external-downloader")
        command_to_exec.append("aria2c")
        command_to_exec.append("--external-downloader-args")
        command_to_exec.append("-x 16 -s 16 -k 1M")

    #
    command_to_exec.append("--no-warnings")
    # command_to_exec.append("--quiet")
    command_to_exec.append("--restrict-filenames")
    #
    if HTTP_PROXY != "":
        command_to_exec.append("--proxy")
        command_to_exec.append(HTTP_PROXY)
    if ".cloud" in yt_dlp_url:
        command_to_exec.append("--referer")
        command_to_exec.append("https://vidmoly.to/")
    if "https://sbthe.com" in yt_dlp_url:
        command_to_exec.append("--referer")
        command_to_exec.append("https://sbthe.com")
    if "closeload" in yt_dlp_url:
        command_to_exec.append("--referer")
        command_to_exec.append("https://closeload.com/")
    if yt_dlp_username is not None:
        command_to_exec.append("--username")
        command_to_exec.append(yt_dlp_username)
    if yt_dlp_password is not None:
        command_to_exec.append("--password")
        command_to_exec.append(yt_dlp_password)
    LOGGER.info(command_to_exec)
    start = datetime.now()
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        # stdout must a pipe to be accessible as process.stdout
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # Wait for the subprocess to finish
    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    t_response = stdout.decode().strip()
    # LOGGER.info(e_response)
    # LOGGER.info(t_response)
    ad_string_to_replace = "please report this issue on  https://github.com/yt-dlp/yt-dlp/issues?q= , filling out the " \
                           "appropriate issue template. Confirm you are on the latest version using  yt-dlp -U "
    if e_response and ad_string_to_replace in e_response:
        error_message = e_response.replace(ad_string_to_replace, "")
        await message.edit_caption(caption=error_message)
        return False, None
    if t_response:
        # LOGGER.info(t_response)
        try:
            os.remove(save_ytdl_json_path)
        except FileNotFoundError as exc:
            pass

        end_one = datetime.now()
        time_taken_for_download = (end_one - start).seconds

        #
        file_size = TG_MAX_FILE_SIZE + 1
        #
        LOGGER.info(tmp_directory_for_each_user)
        user = await bot.get_me()
        BotMention = user.mention
        UserMention = update.from_user.mention

        if PROMO:
            caption += Translation.UPLOADER.format(UserMention, BotMention)
            btn = [[
                InlineKeyboardButton(f"Uploaded By {user.first_name}", url=f"tg://user?id={user.id}")
            ]]
            reply_markup = InlineKeyboardMarkup(btn)
        else:
            reply_markup = False

        if os.path.isdir(tmp_directory_for_each_user):
            directory_contents = os.listdir(tmp_directory_for_each_user)
            directory_contents.sort()
        else:
            try:
                shutil.rmtree(tmp_directory_for_each_user)  # delete folder for user
                os.remove(thumb_image_path)
            except:
                pass

        for single_file in directory_contents:
            print(single_file)
            path = os.path.join(tmp_directory_for_each_user, single_file)

            file_size = os.stat(path).st_size

            try:
                if tg_send_type == 'video' and 'webm' in path:
                    download_directory = path.rsplit('.', 1)[0] + '.mkv'
                    os.rename(path, download_directory)
                    path = download_directory
            except:
                pass

            if file_size > 2093796556:
                is_w_f = False
                images = await generate_screen_shots(
                    path,
                    tmp_directory_for_each_user,
                    is_w_f,
                    DEF_WATER_MARK_FILE,
                    300,
                    9
                )
                try:
                    await bot.edit_message_text(
                        text=Translation.UPLOAD_START,
                        chat_id=chat_id,
                        message_id=message_id
                    )
                except:
                    pass

                start_time = time.time()

                try:
                    if tg_send_type == "audio":
                        duration = await AudioMetaData(path)
                        thumbnail = await DocumentThumb(bot, update)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_AUDIO)
                        copy = await userbot.send_audio(
                            chat_id=PRE_LOG,
                            audio=path,
                            caption=caption,
                            duration=duration,
                            thumb=thumbnail,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    elif tg_send_type == "vm":
                        width, duration = await VMMetaData(path)
                        thumbnail = await VideoThumb(bot, update, duration, path, random)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_VIDEO_NOTE)
                        copy = await userbot.send_video_note(
                            chat_id=PRE_LOG,
                            video_note=path,
                            duration=duration,
                            length=width,
                            thumb=thumbnail,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    elif tg_send_type == "file":
                        copy = await userbot.send_document(
                            chat_id=PRE_LOG,
                            document=path,
                            caption=caption,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    elif (await db.get_upload_as_doc(user_id)) is True:
                        thumbnail = await DocumentThumb(bot, update)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
                        copy = await userbot.send_document(
                            chat_id=PRE_LOG, 
                            document=path,
                            thumb=thumbnail,
                            caption=caption,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    else:
                        width, height, duration = await VideoMetaData(path)
                        thumb_image_path = await VideoThumb(bot, update, duration, path, random)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_VIDEO)
                        copy = await userbot.send_video(
                            chat_id=PRE_LOG,
                            video=path,
                            caption=caption,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                            reply_markup=reply_markup,
                            thumb=thumb_image_path,
                            reply_to_message_id=message.reply_to_message.id,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                       ) 
                    if BOT_PM:
                        await copy.copy(chat_id)
                except Exception as f:
                    bot.send_message(OWNER_ID, f"{f}") 
                    if LOG_CHANNEL:
                        await copy.copy(LOG_CHANNEL)
                except FloodWait as e:
                    print(f"Sleep of {e.value} required by FloodWait ...")
                    time.sleep(e.value)
                except MessageNotModified:
                    pass 
                        return

                end_two = datetime.now()
                time_taken_for_upload = (end_two - end_one).seconds
                media_album_p = []
                try:
                    await bot.edit_message_text(
                        text=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format(time_taken_for_download,
                                                                                time_taken_for_upload),
                        chat_id=chat_id,
                        message_id=message_id,
                        disable_web_page_preview=True
                    )
                except MessageNotModified:
                    pass
                return
            else:
                is_w_f = False
                images = await generate_screen_shots(
                    path,
                    tmp_directory_for_each_user,
                    is_w_f,
                    DEF_WATER_MARK_FILE,
                    300,
                    9
                )
                try:
                    await bot.edit_message_text(
                        text=Translation.UPLOAD_START,
                        chat_id=chat_id,
                        message_id=message_id
                    )
                except:
                    pass

                start_time = time.time()

                try:
                    if tg_send_type == "audio":
                        duration = await AudioMetaData(path)
                        thumbnail = await DocumentThumb(bot, update)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_AUDIO)
                        copy = await userbot.send_audio(
                            chat_id=PRE_LOG,
                            audio=path,
                            caption=caption,
                            duration=duration,
                            thumb=thumbnail,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    elif tg_send_type == "vm":
                        width, duration = await VMMetaData(path)
                        thumbnail = await VideoThumb(bot, update, duration, path, random)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_VIDEO_NOTE)
                        copy = await bot.send_video_note(
                            chat_id=chat_id,
                            video_note=path,
                            duration=duration,
                            length=width,
                            thumb=thumbnail,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    elif tg_send_type == "file":
                        copy = await bot.send_document(
                            chat_id=chat_id,
                            document=path,
                            caption=caption,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    elif (await db.get_upload_as_doc(user_id)) is True:
                        thumbnail = await DocumentThumb(bot, update)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_DOCUMENT)
                        copy = await bot.send_document(
                            chat_id=chat_id, 
                            document=path,
                            thumb=thumbnail,
                            caption=caption,
                            reply_to_message_id=message.reply_to_message.id,
                            reply_markup=reply_markup,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    else:
                        width, height, duration = await VideoMetaData(path)
                        thumb_image_path = await VideoThumb(bot, update, duration, path, random)
                        await message.reply_to_message.reply_chat_action(ChatAction.UPLOAD_VIDEO)
                        copy = await bot.send_video(
                            chat_id=chat_id,
                            video=path,
                            caption=caption,
                            duration=duration,
                            width=width,
                            height=height,
                            supports_streaming=True,
                            reply_markup=reply_markup,
                            thumb=thumb_image_path,
                            reply_to_message_id=message.reply_to_message.id,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                Translation.UPLOAD_START,
                                message,
                                start_time
                            )
                        )
                    if LOG_CHANNEL:
                        await copy.copy(LOG_CHANNEL)
                except FloodWait as e:
                    print(f"Sleep of {e.value} required by FloodWait ...")
                    time.sleep(e.value)
                except MessageNotModified:
                    pass
                end_two = datetime.now()
                time_taken_for_upload = (end_two - end_one).seconds
                media_album_p = []
                try:
                    await bot.edit_message_text(
                        text=Translation.AFTER_SUCCESSFUL_UPLOAD_MSG_WITH_TS.format(time_taken_for_download,
                                                                                time_taken_for_upload),
                        chat_id=chat_id,
                        message_id=message_id,
                        disable_web_page_preview=True
                    )
                except MessageNotModified:
                    pass
                return

                end_two = datetime.now()
                time_taken_for_upload = (end_two - end_one).seconds
                media_album_p = []
                if (await db.get_generate_ss(user_id)) is True:
                    if images is not None:
                        i = 0
                        caption = BotMention
                        for image in images:
                            if os.path.exists(str(image)):
                                if i == 0:
                                    media_album_p.append(
                                        InputMediaPhoto(
                                            media=image,
                                            caption=caption
                                        )
                                    )
                                else:
                                    media_album_p.append(
                                        InputMediaPhoto(
                                            media=image
                                        )
                                    )
                                i = i + 1
                    await bot.send_media_group(
                        chat_id=chat_id,
                        disable_notification=True,
                        reply_to_message_id=message_id,
                        media=media_album_p
                    )
            #
    try:
        os.remove(thumb_image_path)
    except:
        pass
    try:
        shutil.rmtree(tmp_directory_for_each_user)
    except:
        pass
    try:
        os.remove(path)
    except:
        pass
