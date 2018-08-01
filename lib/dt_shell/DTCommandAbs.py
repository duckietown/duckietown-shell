from abc import ABCMeta, abstractmethod

class DTCommandAbs(object):
    __metaclass__ = ABCMeta

    name = None
    commands = None
    fake = False

    @staticmethod
    @abstractmethod
    def command(shell, word):
        pass

    @staticmethod
    def do_command(cls, shell, line):
        print '>[%s]@(%s, %s)' % (line, cls.name, cls.__class__)
        line = line.strip()
        parts = [ p.strip() for p in line.split(' ') ]
        word = parts[0]
        args = parts[1:]
        print '[%s, %r]@(%s, %s)' % (word, args, cls.name, cls.__class__)
        if len(word) > 0:
            #
            if len(cls.commands) > 0:
                if word in cls.commands:
                    cls.commands[word].do_command(cls.commands[word], shell, ' '.join(args))
                else:
                    print 'Command `%s` not recognized.\nAvailable sub-commands are:\n\n\t%s' % ( word.strip(), '\n\t'.join(cls.commands.keys()) )
            else:
                cls.command(shell, args)
        else:
            if len(cls.commands) > 0:
                print 'Available sub-commands are:\n\n\t%s' % '\n\t'.join(cls.commands.keys())
            else:
                if not cls.fake:
                    cls.command(shell, args)

    @staticmethod
    def complete_command(cls, shell, word, line, start_index, end_index):
        print '[%s](%s)@(%s, %s)' % (word, line, cls.name, cls.__class__)
        word = word.strip()
        line = line.strip()
        subcmds = [ k+' ' for k in cls.commands.keys() ]
        parts = [ p.strip() for p in line.split(' ') ]
        #
        if len(word) <= 0:
            # there is no partial word
            last_cmd = word if len(word)>0 else line.split(' ')[-1]
            if last_cmd != cls.name:
                if last_cmd in cls.commands.keys():
                    print '!A'
                    return DTCommandAbs.complete_command(cls.commands[last_cmd], shell, "", line, start_index, end_index)
            else:
                # I'm in the same object identified by the last word on the line
                print '!B'
                return subcmds
        else:
            # there is a partial word
            if parts[0] == cls.name and len(parts) > 2 and parts[1] in cls.commands.keys():
                print '!E'
                return DTCommandAbs.complete_command(cls.commands[parts[1]], shell, parts[-1], ' '.join(parts[1:]), start_index, end_index)
            else:
                comp_subcmds = [ k for k in subcmds if k.startswith(word) ]
                print '!C'
                return comp_subcmds
        print '!D'
        return []
