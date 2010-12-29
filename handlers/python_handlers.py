from dexy.handler import DexyHandler
import shutil

class CopyHandler(DexyHandler):
    INPUT_EXTENSIONS = [".*"]
    OUTPUT_EXTENSIONS = [".*"]
    ALIASES = ['cp']
    
    # Just copy the file without trying to read the contents. 
    # Rather hacky, needs testing to figure out implications for caching.
    def process(self):
        self.artifact.auto_write_artifact = False
        shutil.copyfile(self.doc.name, self.artifact.filename())

class JoinHandler(DexyHandler):
    """ This handler is so people have to acknowledge when they pass sectioned
    text through a filter which doesn't preserve sectioning."""
    INPUT_EXTENSIONS = [".*"]
    OUTPUT_EXTENSIONS = [".*"]
    ALIASES = ['join']

    def process_dict(self, input_dict):
        return {'1' : self.artifact.input_text()}

class FooterHandler(DexyHandler):
    INPUT_EXTENSIONS = [".*"]
    OUTPUT_EXTENSIONS = [".*"]
    ALIASES = ['ft', 'footer']

    def process_text(self, input_text):
        self.artifact.load_input_artifacts()
        footer_key = "_footer%s" % self.artifact.ext
        footer_keys = []
        for k in self.artifact.input_artifacts_dict.keys():
            contains_footer = k.find(footer_key) > 0
            contains_pyg = k.find('|pyg') > 0
            if contains_footer and not contains_pyg:
                footer_keys.append(k)

        if len(footer_keys) > 0:
            footer_key = sorted(footer_keys)[-1]
            footer_text = self.artifact.input_artifacts_dict[footer_key]['data']
        else:
            raise Exception("No file matching %s was found to work as a footer." % footer_key)
                            
        return "%s\n%s" % (input_text, footer_text)

class HeaderHandler(DexyHandler):
    INPUT_EXTENSIONS = [".*"]
    OUTPUT_EXTENSIONS = [".*"]
    ALIASES = ['hd', 'header']

    def process_text(self, input_text):
        self.artifact.load_input_artifacts()
        header_key = "_header%s" % self.artifact.ext
        header_keys = []
        for k in self.artifact.input_artifacts_dict.keys():
            contains_header = k.find(header_key) > 0
            contains_pyg = k.find('|pyg') > 0
            if contains_header and not contains_pyg:
                header_keys.append(k)
        if len(header_keys) > 0:
            header_key = sorted(header_keys)[-1]
            header_text = self.artifact.input_artifacts_dict[header_key]['data']
        else:
            raise Exception("No file matching %s was found to work as a header for %s." % (header_key, self.artifact.key))
                            
        return "%s\n%s" % (header_text, input_text)

# TODO implement combined header/footer handler as a shortcut

### @export "head-handler"
class HeadHandler(DexyHandler):
    ALIASES = ['head']
    def process_text(self, input_text):
        return "\n".join(input_text.split("\n")[0:10]) + "\n"

### @export "word-wrap"
class WordWrapHandler(DexyHandler):
    ALIASES = ['ww', 'wrap']

    #http://code.activestate.com/recipes/148061-one-liner-word-wrap-function/
    def wrap_text(self, text, width):
        """
        A word-wrap function that preserves existing line breaks
        and most spaces in the text. Expects that existing line
        breaks are posix newlines (\n).
        """
        return reduce(lambda line, word, width=width: '%s%s%s' %
                 (line,
                   ' \n'[(len(line)-line.rfind('\n')-1
                         + len(word.split('\n',1)[0]
                              ) >= width)],
                   word),
                  text.split(' ')
                 )

    def process_text(self, input_text):
        return self.wrap_text(input_text, 79)
