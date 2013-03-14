import logging
import operator
import random
import re

import irc.bot

import calculations
import config
import textdb
import user_utils
from decorators import nick_command, stats_command


logger = logging.getLogger(__name__)

class RehaikuBot(irc.bot.SingleServerIRCBot):
    def __init__(self, server_list, nick, name, channel, recon_interval=60, **connect_params):
        super(RehaikuBot, self).__init__(server_list, nick, name, recon_interval, **connect_params)
        self.channel = channel
        self.cmds = ['stats', 'haiku', 'replay', 'conv', 'pretentious', 'leaderboard', 'loserboard', 'percentlol', 'spammy']
        self.db = textdb.TextDb()


    def on_welcome(self, c, e):
        logger.info("Connected to %s", e.source)
        c.join(self.channel)


    def on_join(self, c, e):
        logger.info("Joined channel %s", e.target)


    def on_pubmsg(self, c, e):
        logger.debug("Got public msg {} (from {}, to {})".format(e.arguments, e.source.nick, e.target))
        self._process_msg(e.target, e)


    def on_privmsg(self, c, e):
        pass # ignore PMs
        #logger.debug("Got private msg {} (from {}, to {})".format(e.arguments, e.source.nick, e.target))
        #self._process_msg(e.source.nick, e)


    def _process_msg(self, respond_target, e):
        full_text = e.arguments[0]
        cmd,arguments = self._get_cmd(full_text)
        if cmd != None:
            self._process_cmd(respond_target, cmd, arguments, e)
        elif full_text[:1] not in config.ignore_prefixes:
            self._process_text(e)


    def _process_text(self, e):
        txt = e.arguments[0]
        logger.debug("_process_text: " + txt)
        self.db.add_line(e.source.nick, e.target, txt)


    def _get_cmd(self, cmd):
        if cmd[:1] == config.cmd_prefix:
            cmd_boundary = cmd.find(' ')
            cmd = cmd[1:]
            cmd_name = cmd
            arguments = ""
            if cmd_boundary != -1:
                cmd_name = cmd[:cmd_boundary].strip()
                arguments = cmd[cmd_boundary:].strip()

            if cmd_name in self.cmds:
                logger.info("got command name " + cmd_name + " " + arguments)
                return cmd_name,arguments

        return None,None


    def _process_cmd(self, respond_target, cmd, arguments, e):
        logger.debug("_process_cmd: {} ({})".format(cmd, arguments))
        getattr(self, '_do_' + cmd)(respond_target, cmd, arguments, e)


    @nick_command
    @stats_command('I have collected {} lines of dialog from {}.')
    def _do_stats(self, respond_target, cmd, arguments, e, nick):
        logger.debug("_do_stats")
        return "stats"


    def _do_haiku(self, respond_target, cmd, arguments, e):
        arguments = arguments.split()

        if len(arguments) > 0:
            return

        logger.debug("_do_haiku")
        self.connection.privmsg(respond_target, "I'm sorry, Dave. I'm afraid I can't do that.")


    @nick_command
    def _do_replay(self, respond_target, cmd, arguments, e, nick):
        logger.debug("_do_replay")

        line = self.db.get_random_line(nick,e.target)
        if line != None:
            self.connection.privmsg(respond_target, "<{}> {}".format(nick, line))
        else:
            self.connection.privmsg(respond_target, "{} has no history!".format(nick))

    @nick_command
    def _do_conv(self, respond_target, cmd, arguments, e, nick):
        logger.debug("_do_conv")

        nick_match = None
        tries = 20
        while not nick_match:
            line = self.db.get_random_line_like(nick, e.target, '%:%')
            if line is None:  # no directed lines by the user
                logger.debug('No directed lines by the user')
                return
            nick_match = re.match('([^:]*):', line)
            logger.debug(nick_match)
            tries -= 1
            if tries == 0:
                logger.debug(line)
                logger.warning(
                    "Something's gone horribly wrong. " +
                    "Giving up on conversation"
                )
                return

        self.connection.privmsg(respond_target, "<{}> {}".format(nick, line))

        if nick_match:
            next_nick = nick_match.group(1)
            if random.randint(0, 5) == 0:
                # 1/6 chance that we end the conversation means average
                # conversation length is 5 lines
                line = self.db.get_random_line(next_nick, e.target)
                self.connection.privmsg(
                    respond_target, "<{}> {}".format(next_nick, line)
                )
            else:
                self._do_conv(respond_target, cmd, arguments, e, next_nick)
        else:
            logger.error(
                ('''"{}" contains a nick according to the database, ''' +
                 '''but it really doesn't''').format(line))

    def _do_leaderboard(self, respond_target, cmd, arguments, e):
        logger.debug("_do_leaderboard")

        arguments = arguments.split()
        if len(arguments) != 1:
            return

        stat_name = arguments[0]

        return self._leaderboard(respond_target, stat_name, False)


    def _do_loserboard(self, respond_target, cmd, arguments, e):
        logger.debug("_do_loserboard")

        arguments = arguments.split()
        if len(arguments) != 1:
            return

        stat_name = arguments[0]

        return self._leaderboard(respond_target, stat_name, True)


    def _leaderboard(self, respond_target, stat_name, reverse):
        if stat_name == 'pretentious':
            return

        try:
            stat_func = getattr(calculations, stat_name)
        except AttributeError:
            return

        nicks = user_utils.active_users(self.db)
        stats = dict()
        for nick in nicks:
            stats[nick] = round(stat_func(self.db, nick), 2)

        all = sorted(stats.items(), key=operator.itemgetter(1), reverse=not reverse)
        name = 'leaderboard'
        if reverse:
            name = 'loserboard'
        self.connection.privmsg(respond_target, "{} for {}:".format(name, stat_name))
        num = min(len(all), 5)
        for i in range(num):
            self.connection.privmsg(respond_target, "{:20}: {:6}".format(all[i][0], all[i][1]))


    @nick_command
    @stats_command("{1}'s pretentiousness level is {0:.3}")
    def _do_pretentious(self, respond_target, cmd, arguments, e, nick):
        logger.debug("_do_pretentious")
        return "pretentious"


    @nick_command
    @stats_command("{1}'s lol percentage is {0:.3}")
    def _do_percentlol(self, respond_target, cmd, arguments, e, nick):
        logger.debug('_do_percentlol')
        return 'percentlol'


    @nick_command
    @stats_command("{1}'s spamminess is {0:.3}")
    def _do_spammy(self, respond_target, cmd, arguments, e, nick):
        logger.debug('_do_spammy')
        return 'spammy'
