import datetime
import json
import logging
import os
import pathlib
import sys
import time

import telegram.ext
from telegram.ext.filters import Filters

from dfrotz import DFrotz
import models
import parser

logging.basicConfig(
    format='[%(asctime)s-%(name)s-%(levelname)s]\n%(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.DEBUG,
)
logging.getLogger('telegram').setLevel(logging.WARNING)

def log_dialog(in_message, out_message):
    logging.info('@%s[%d] sent: %r' % (
        in_message.from_user.username,
        in_message.from_user.id,
        in_message.text[:40])
    )
    logging.info('Answering @%s[%d]: %r' % (
        in_message.from_user.username,
        in_message.from_user.id,
        out_message.text[:40] if out_message is not None else '[None]')
    )

def on_error(bot, update, error):
    logger = logging.getLogger(__name__)
    logger.warn('Update %r caused error %r!' % (update, error))
    print(error)

def cmd_default(bot, message, z5bot, chat):
    # gameplay messages will be sent here
    text = message.text.strip().lower()

    if any(cmd in text for cmd in ["load", "restore"]):
        text = '(Note: use /load.)'
        bot.sendMessage(message.chat_id, text)
        if not chat.has_story():
            return

    if any(cmd in text for cmd in ["save", "dump", "backup"]):
        text = '(Note: use /save.)'
        bot.sendMessage(message.chat_id, text)
        if not chat.has_story():
            return

    if text.startswith('/msg'):
        text = text.split(maxsplit=1)[1]

    if not chat.has_story():
        text = 'Please use the /select command to select a game.'
        return bot.sendMessage(message.chat_id, text)

    # here, stuff is sent to the interpreter
    z5bot.process(message.chat_id, text)

    received = z5bot.receive(message.chat_id)
    reply = bot.sendMessage(message.chat_id, received, parse_mode='HTML')
    log_dialog(message, reply)

    if ' return ' in received.lower() or ' enter ' in received.lower():
        notice = '(Note: You are able to do use the return key by typing /enter.)'
        return bot.sendMessage(message.chat_id, notice)

def cmd_start(bot, message, *args):
    text =  'Welcome, %s!\n' % message.from_user.first_name
    text += 'Please use the /select command to select a game.\n'
    return bot.sendMessage(message.chat_id, text, parse_mode='HTML')

def cmd_select(bot, message, z5bot, chat):
    selection = 'For "%s", write /select %s.'
    msg_parts = []
    for story in models.Story.instances:
        part = selection % (story.name, story.abbrev)
        msg_parts.append(part)
    text = '\n'.join(msg_parts)

    for story in models.Story.instances:
        if ' ' in message.text and message.text.strip().lower().split(' ')[1] == story.abbrev:
            chat.set_story(models.Story.get_instance_by_abbrev(story.abbrev))
            z5bot.add_chat(chat)
            reply = bot.sendMessage(message.chat_id, '<pre>Starting "%s"...</pre>' % story.name, parse_mode='HTML')
            log_dialog(message, reply)
            notice  = '<pre>Your progress will be saved automatically.</pre>'
            reply = bot.sendMessage(message.chat_id, notice, parse_mode='HTML')
            log_dialog(message, reply)
            reply = bot.sendMessage(message.chat_id, z5bot.receive(message.chat_id), parse_mode='HTML')
            log_dialog(message, reply)
            return

    return bot.sendMessage(message.chat_id, text)

def cmd_load(bot, message, z5bot, chat):
    if not chat.has_story():
        text = '<pre>You have to select a game first.</pre>'
        return bot.sendMessage(message.chat_id, text, parse_mode='HTML')

    # Todo: match a RegEx against user input. z5bot should not leak my
    # secret files about MKULTRA.
    savefile = message.text.split(maxsplit=1)[1]
    for command in ["restore", chat.savedir.joinpath(savefile)]:
        z5bot.process(message.chat_id, command)

    if "ok" in z5bot.receive(message.chat_id).lower():
        return bot.sendMessage(message.chat_id, "<pre>Restored the game.</pre>", parse_mode='HTML')
    else:
        return bot.sendMessage(message.chat_id, "<pre>Something went wrong.</pre>", parse_mode='HTML')


def cmd_save(bot, message, z5bot, chat):
    if not chat.has_story():
        text = '<pre>You have to play a game first.</pre>'
        return bot.sendMessage(message.chat_id, text, parse_mode='HTML')

    savefile = datetime.datetime.now().strftime("%y%m%d-%H%M") + ".qzl"
    for command in ["save", chat.savedir.joinpath(savefile)]:
        z5bot.process(message.chat_id, command)

    if "ok" in z5bot.receive(message.chat_id).lower():
        return bot.sendMessage(message.chat_id, "<pre>Saved. Restore via /load %s.</pre>" % savefile, parse_mode='HTML')
    else:
        return bot.sendMessage(message.chat_id, "<pre>Something went wrong.</pre>", parse_mode='HTML')

def cmd_clear(bot, message, z5bot, chat):
    return bot.sendMessage(message.chat_id, "This is a stub.")

def cmd_enter(bot, message, z5bot, chat):
    if not chat.has_story():
        return

    command = '' # \r\n is automatically added by the Frotz abstraction layer
    z5bot.process(message.chat_id, command)
    return bot.sendMessage(message.chat_id, z5bot.receive(message.chat_id))

def cmd_ignore(*args):
    return

def cmd_ping(bot, message, *args):
    return bot.sendMessage(message.chat_id, 'Pong!')

def cmd_msg(bot, message, z5bot, chat):
    return cmd_default(bot, message, z5bot, chat) 

def on_message(update, callback_context):
    message = update.message
    z5bot = models.Z5Bot.get_instance_or_create()
    func = z5bot.parser.get_function(message.text)
    chat = models.Chat.get_instance_or_create(message.chat_id)
    out_message = func(callback_context.bot, message, z5bot, chat)

    log_dialog(message, out_message)

if __name__ == '__main__':
    with open('config.json', 'r') as f:
        config = json.load(f)

    api_key = config['api_key']
    logging.info('Logging in with api key %r.' % api_key)
    if len(sys.argv) > 1:
        logging.info('Broadcasting is available! Send /broadcast.')

    for story in config['stories']:
        models.Story(
            name=story['name'],
            abbrev=story['abbrev'],
            filename=story['filename']
        )

    z5bot = models.Z5Bot.get_instance_or_create()
    z5bot.set_cwd(pathlib.Path.cwd())

    p = parser.Parser()
    p.add_default(cmd_default)
    p.add_command('/start', cmd_start)
    p.add_command('/select', cmd_select)
    p.add_command('/load', cmd_load)
    p.add_command('/save', cmd_save)
    p.add_command('/clear', cmd_clear)
    p.add_command('/enter', cmd_enter)
    p.add_command('/i', cmd_ignore)
    p.add_command('/ping', cmd_ping)
    p.add_command('/msg',cmd_msg)
    z5bot.add_parser(p)


    updater = telegram.ext.Updater(api_key, use_context=True)
    dispatcher = updater.dispatcher
    # Make sure the user's messages get redirected to our parser,
    # with or without a slash in front of them.
    dispatcher.add_handler(telegram.ext.MessageHandler(Filters.all, callback=on_message))
    dispatcher.add_error_handler(callback=on_error)
    updater.start_polling()
