"""
Analyzer - performs analysis throughout trajectory.
"""
import logging
from collections import namedtuple

from .molecules import Molecule

__all__ = ['Analyzer', 'Step']


LOGGER = logging.getLogger(__name__)


class Step(object):
    """
    Container with information about ongoing analysis.

    @ivar molecule: Molecule object
    @ivar frame: Currently analyzed frame (total count).
    """
    def __init__(self, molecule):
        self.molecule = molecule
        # Total frame count
        self.frame = -1
        # Frame number of the currently loaded frame
        self._chunk_frame = -1

    def __repr__(self):
        return '<%s: %d>' % (type(self).__name__, self.frame)

    def __str__(self):
        return 'Step %d' % self.frame

    def next_chunk(self):
        """
        New chunk is loaded.
        """
        self._chunk_frame = -1

    def next_frame(self):
        """
        Move to the next frame.
        """
        self.frame += 1
        self._chunk_frame += 1
        self.molecule.frame = self._chunk_frame


# Internal structure which maintains callback information in analyzer
Callback = namedtuple('Callback', ('function', 'args', 'kwargs'))


class Analyzer(object):
    """
    Iteratively loads the trajectory files and performs analysis.
    """
    def __init__(self, molecule, traj_files, filetype=None, step=1, chunk=100):
        """
        @param molecule: Molecule used for loading the trajectory.
        @param traj_files: List of trajectory files
        @param filetype: Format of file. If not present or `None` it is guessed.
        @type filetype: One of `molecules.FORMAT_` constants, string or `None`
        @param step: Load every 'step'th frame from trajectory.
        @type step: Positive integer
        @param chunk: Number of frames to load at once
        @type chunk: Positive integer
        """
        assert isinstance(molecule, Molecule)
        assert step > 0
        assert chunk > 0
        self.molecule = molecule
        self.traj_files = traj_files
        self.step = step
        self.chunk = chunk
        self._callbacks = []
        self.filetype = filetype

    def add_callback(self, callback, *args, **kwargs):
        """
        Add callback to be called on every frame.

        @param callback: A function to be called on every step. It must expect `Step` object as first argument.
        @param *args: Additional positional arguments a function is called with.
        @param **kwargs: Additional keyword arguments a function is called with.
        """
        self._callbacks.append(Callback(callback, args, kwargs))

    def add_dataset(self, dataset):
        """
        Registers dataset for analysis.
        """
        self._callbacks.append(Callback(dataset.collect, (), {}))

    def analyze(self):
        """
        Run the analysis.
        """
        # Clear the molecule frames
        del self.molecule.frames[:]

        step = Step(self.molecule)
        for filename in self.traj_files:
            start = 0
            while True:
                # Load 'chunk' frames
                stop = start + self.step * self.chunk - 1
                LOGGER.debug('Loading %s from %d to %d, every %d', filename, start, stop, self.step)
                self.molecule.load(filename, filetype=self.filetype, start=start, stop=stop, step=self.step)
                loaded = len(self.molecule.frames)
                if not loaded:
                    # No frames were loaded
                    break

                # Call the callback
                step.next_chunk()
                for dummy in xrange(0, loaded):
                    step.next_frame()
                    LOGGER.info('Analyzing frame %d', step.frame)
                    for callback in self._callbacks:
                        callback.function(step, *callback.args, **callback.kwargs)

                # Prepare for next iteration - delete all frames
                del self.molecule.frames[:]
                if loaded < self.chunk:
                    # Nothing else to be loaded for this filename
                    break
                start += self.step * self.chunk
        LOGGER.info('Analyzed %s frames.', step.frame + 1)
