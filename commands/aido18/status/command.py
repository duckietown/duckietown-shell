from dt_shell import DTCommandAbs

class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell, args):
        print 'This is status, and I got the arguments `%r`' % args
