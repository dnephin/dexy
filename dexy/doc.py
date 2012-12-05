import dexy.artifact
import dexy.exceptions
import dexy.filter
import dexy.task
import fnmatch
import os
import posixpath
import re

class Doc(dexy.task.Task):
    """
    Task subclass representing Documents.
    """
    ALIASES = ['doc']

    @classmethod
    def filter_class_for_alias(klass, alias):
        if alias == '':
            raise dexy.exceptions.BlankAlias
        elif alias.startswith("-"):
            return dexy.filter.DexyFilter
        else:
            try:
                return dexy.filter.Filter.aliases[alias]
            except KeyError:
                msg = "Dexy doesn't have a filter '%s' available." % alias

                all_plugins = dexy.filter.Filter.aliases.values()
                num_plugins = len(all_plugins)
                if num_plugins < 10:
                    plugin_list = ", ".join(p.__name__ for p in all_plugins)
                    msg += " Note that only %s plugins are available: %s" % (num_plugins, plugin_list)
                    msg += " There may be a problem loading plugins, adding 'import dexy.plugins' might help."

                raise dexy.exceptions.UserFeedback(msg)

    def websafe_key(self):
        return self.key.replace("/", "--")

    def intersect_children_deps(self):
        children_deps = list(set(self.children).intersection(self.deps.values()))
        import operator
        return sorted(children_deps, key=operator.attrgetter('key_with_class'))

    def names_to_docs(self):
        """
        Returns a dict whose keys are canonical names, whose values are lists
        of the docs that generate that name as their canonical output name.
        """
        names_to_docs = {}
        for doc in self.completed_child_docs():
            doc_name = doc.output().name
            if names_to_docs.has_key(doc_name):
                names_to_docs[doc_name].append(doc)
            else:
                names_to_docs[doc_name] = [doc]
        return names_to_docs

    def conflicts(self):
        """
        List of inputs to document where more than 1 doc generates same
        canonical filename.
        """
        conflicts = {}
        for k, v in self.names_to_docs().iteritems():
            if len(v) > 1:
                conflicts[k] = v
        return conflicts

    def is_index_page(self):
        fn = self.output().name
        # TODO index.json only if htmlsections in doc key..
        return fn.endswith("index.html") or fn.endswith("index.json")

    def title(self):
        if self.args.get('title'):
            return self.args.get('title')
        elif self.is_index_page():
            # use subdirectory we're in
            return posixpath.split(posixpath.dirname(self.name))[-1].capitalize()
        else:
            return self.name

    def output(self):
        """
        Returns a reference to the output_data Data object generated by the final filter.
        """
        final_state = self.final_artifact.state
        if not final_state == 'complete':
            if not final_state == 'setup' and len(self.filters) == 0:
                raise dexy.exceptions.InternalDexyProblem("Final artifact state is '%s'" % self.final_artifact.state)

        return self.final_artifact.output_data

    def setup_initial_artifact(self):
        if os.path.exists(self.name):
            initial = dexy.artifact.InitialArtifact(self.name, wrapper=self.wrapper)
        else:
            initial = dexy.artifact.InitialVirtualArtifact(self.name, wrapper=self.wrapper)

        initial.args = self.args
        initial.name = self.name
        initial.prior = None
        initial.doc = self
        initial.remaining_doc_filters = self.filters
        initial.created_by_doc = self.created_by_doc
        initial.transition('populated')

        self.children.append(initial)
        self.artifacts.append(initial)
        self.final_artifact = initial

    def setup_filter_artifact(self, key, filters):
        artifact = dexy.artifact.FilterArtifact(key, wrapper=self.wrapper)

        # Remove args that are only relevant to the doc or to the initial artifact.
        filter_artifact_args = self.args.copy()
        for k in ['contents', 'contentshash', 'data-class-alias', 'depends']:
            if filter_artifact_args.has_key(k):
                del filter_artifact_args[k]

        artifact.args = filter_artifact_args

        artifact.doc = self
        artifact.remaining_doc_filters = self.filters[len(filters):len(self.filters)]
        artifact.filter_alias = filters[-1]
        artifact.doc_filepath = self.name
        artifact.prior = self.artifacts[-1]
        artifact.created_by_doc = self.created_by_doc
        artifact.transition('populated')

        try:
            artifact.filter_class = self.filter_class_for_alias(filters[-1])
        except dexy.exceptions.BlankAlias:
            raise dexy.exceptions.UserFeedback("You have a trailing | or you have 2 | symbols together in your specification for %s" % self.key)

        if not artifact.filter_class.is_active():
            raise dexy.exceptions.InactiveFilter(artifact.filter_alias, artifact.doc.key)

        artifact.filter_instance = artifact.filter_class()
        artifact.filter_instance.artifact = artifact
        artifact.set_log()
        artifact.log.addHandler(self.log.handlers[0])
        artifact.filter_instance.log = artifact.log

        artifact.next_filter_alias = None
        artifact.next_filter_class = None
        artifact.next_filter_name = None

        if len(filters) < len(self.filters):
            next_filter_alias = self.filters[len(filters)]
            artifact.next_filter_alias = next_filter_alias
            artifact.next_filter_class = self.filter_class_for_alias(next_filter_alias)
            artifact.next_filter_name = artifact.next_filter_class.__name__

        self.children.append(artifact)
        self.artifacts.append(artifact)
        self.final_artifact = artifact

    def setup(self):
        self.hashstring = self.final_artifact.hashstring

    def metadata(self):
        return self.final_artifact.metadata

    def populate(self):
        self.set_log()
        self.name = self.key.split("|")[0]
        self.filters = self.key.split("|")[1:]
        self.artifacts = []
        self.canon = self.args.get('canon', len(self.filters) == 0)

        self.setup_initial_artifact()

        for i in range(0,len(self.filters)):
            filters = self.filters[0:i+1]
            key = "%s|%s" % (self.name, "|".join(filters))
            self.setup_filter_artifact(key, filters)
            self.canon = self.canon or (not self.final_artifact.filter_class.FRAGMENT)

class PatternDoc(dexy.task.Task):
    """
    A doc which takes a file matching pattern and creates individual Doc objects for all files that match the pattern.
    """
    ALIASES = ['pattern']

    def setup(self):
        self.hashstring = ''

    def populate(self):
        self.set_log()
        self.file_pattern = self.key.split("|")[0]
        self.filter_aliases = self.key.split("|")[1:]

        import copy
        orig_doc_children = copy.copy(self.children)
        doc_children = None

        recurse = self.args.get('recurse', True)
        for dirpath, filename in self.wrapper.walk(".", recurse):
            raw_filepath = os.path.join(dirpath, filename)
            filepath = os.path.normpath(raw_filepath)

            if fnmatch.fnmatch(filepath, self.file_pattern):
                except_p = self.args.get('except')
                if except_p and re.search(except_p, filepath):
                    self.log.debug("skipping file '%s' because it matches except '%s'" % (filepath, except_p))
                else:
                    if len(self.filter_aliases) > 0:
                        doc_key = "%s|%s" % (filepath, "|".join(self.filter_aliases))
                    else:
                        doc_key = filepath

                    doc_args = self.args.copy()
                    doc_args['wrapper'] = self.wrapper

                    if doc_args.has_key('depends'):
                        if doc_args.get('depends'):
                            doc_children = self.wrapper.registered_docs()
                        else:
                            doc_children = []
                        del doc_args['depends']

                    self.log.debug("creating child of patterndoc %s: %s" % (self.key, doc_key))
                    if not doc_children:
                        doc_children=orig_doc_children
                    doc = Doc(doc_key, *doc_children, **doc_args)
                    self.children.append(doc)
                    doc.populate()
                    doc.transition('populated')

class BundleDoc(dexy.task.Task):
    """
    A doc which represents a collection of docs.
    """
    ALIASES = ['bundle']

    def populate(self):
        self.set_log()

    def setup(self):
        self.hashstring = ''
