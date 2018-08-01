from dt_shell import DTCommandAbs

class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell, line):
        print 'This is init'

    @staticmethod
    def do_command(cls, shell, word):
        return ['cane', 'gatto']
