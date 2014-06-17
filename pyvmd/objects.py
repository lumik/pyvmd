"""
High level interface to the VMD objects.
"""
import logging
import os.path

from Molecule import Molecule as _Molecule
import VMD


LOGGER = logging.getLogger(__name__)

# File formats
FORMAT_DCD = 'dcd'
FORMAT_PDB = 'pdb'
FORMAT_PSF = 'psf'
# Dictionary to translate file extensions to file formats
FORMATS = {
    'dcd': FORMAT_DCD,
    'pdb': FORMAT_PDB,
    'psf': FORMAT_PSF,
}


def guess_file_format(filename):
    """
    Returns format of the file by guess.

    If format can't be detected returns None.
    """
    dummy, ext = os.path.splitext(filename)
    if not ext or ext == '.':
        return None
    ext = ext[1:]
    # If the extension is not found in dictionary, return it as is
    return FORMATS.get(ext, ext)


class Frames(object):
    """
    Wrapper for molecules' frames.
    """
    def __init__(self, molecule):
        """
        @param molecule: Respective molecule
        @type molecule: Molecule
        """
        # Use molecule instance instead of molid for possible callbacks
        assert isinstance(molecule, Molecule)
        self.molecule = molecule

    def __len__(self):
        return VMD.molecule.numframes(self.molecule.molid)

    def __delitem__(self, key):
        #XXX: For some reason, 'skip' in the 'delframe' function means which frames are left when deleting
        # That is not consistent with python slicing, so we have to avoid that argument
        if isinstance(key, slice):
            start, stop, step = key.indices(len(self))
            # We will delete one by one, so we have to that in reversed order
            frames = reversed(xrange(start, stop, step))
        elif isinstance(key, int):
            if key < 0:
                frames = [len(self) + key]
            else:
                frames = [key]
        else:
            raise TypeError("%s indices must be integers, not %s" % (type(self), type(key)))

        for frame in frames:
            LOGGER.debug("Deleting frame %d", frame)
            VMD.molecule.delframe(self.molecule.molid, beg=frame, end=frame)

    def __iter__(self):
        # Return the iterator over frames
        return iter(xrange(len(self)))

    def copy(self, frame=None):
        """
        Copies frame and moves the molecule to the new frame.
        """
        if frame is None:
            frame = self.molecule.frame
        else:
            assert isinstance(frame, int) and frame >= 0
        VMD.molecule.dupframe(self.molecule.molid, frame)


class Molecule(object):
    """
    Molecule representation.

    This class is a proxy for molecule loaded into VMD.
    """
    def __init__(self, molid):
        """
        Creates a new molecule.

        @param molid: Molecule ID
        """
        assert isinstance(molid, int) and molid >= 0
        if not VMD.molecule.exists(molid):
            raise ValueError("Molecule %d does not exist." % molid)
        self.molid = molid
        self._molecule = None

    def __eq__(self, other):
        return type(self) == type(other) and self.molid == other.molid

    def __ne__(self, other):
        return not self.__eq__(other)

    @classmethod
    def create(cls, name=None):
        """
        Creates new molecule.

        @name: Name of the molecule.
        """
        molid = VMD.molecule.new(name or 'molecule')
        return cls(molid)

    def delete(self):
        """
        Deletes the molecule.
        """
        VMD.molecule.delete(self.molid)

    def load(self, filename, filetype=None, start=0, stop=-1, step=1, wait=True, volsets=None):
        """
        Loads data from file into the molecule.

        @param filename: Name of file to be loaded
        @param filetype: Format of file. If not present it is guessed.
        @param wait: Whather to wait until file is completely loaded.
        """
        assert isinstance(start, int) and start >= 0
        assert isinstance(stop, int) and stop >= -1
        assert isinstance(step, int) and step > 0
        if filetype is None:
            filetype = guess_file_format(filename)
            if filetype is None:
                raise ValueError("Cannot detect filetype for '%s'" % filename)
        waitfor = wait and -1 or 0
        volsets = volsets or []
        VMD.molecule.read(self.molid, filetype, filename, beg=start, end=stop, skip=step, waitfor=waitfor,
                          volsets=volsets)

    @property
    def molecule(self):
        """
        Returns respective VMD.Molecule instance.
        """
        if self._molecule is None:
            self._molecule = _Molecule(id=self.molid)
        return self._molecule

    def _get_frame(self):
        return VMD.molecule.get_frame(self.molid)

    def _set_frame(self, frame):
        assert isinstance(frame, int) and frame >= 0
        VMD.molecule.set_frame(self.molid, frame)

    frame = property(_get_frame, _set_frame, doc="Molecule's frame")

    @property
    def frames(self):
        """
        Returns frames descriptor.
        """
        return Frames(self)

    def _get_name(self):
        return VMD.molecule.name(self.molid)

    def _set_name(self, name):
        VMD.molecule.rename(self.molid, name)

    name = property(_get_name, _set_name, doc="Molecule's name")


class _MoleculeManager(object):
    """
    Manager of all molecules.
    """
    def __init__(self):
        self._names = {}
        # Fill the cache
        self._update()

    def _update(self):
        # Update the name cache
        cache = {}
        for molid in VMD.molecule.listall():
            name = VMD.molecule.name(molid)
            cache.setdefault(name, molid)
        self._names = cache

    def __len__(self):
        return VMD.molecule.num()

    def __getitem__(self, key):
        """
        Returns molecule specified by name or molid.

        If name is not unique, the molecule returned is not defined.

        @type key: int or str
        @rtype: Molecule
        """
        if isinstance(key, int):
            assert key >= 0
            if VMD.molecule.exists(key):
                return Molecule(key)
            else:
                raise ValueError("Molecule %d doesn't exist." % key)
        elif isinstance(key, basestring):
            # First check the cached names
            if key in self._names:
                molid = self._names[key]
                if VMD.molecule.exists(molid):
                    return Molecule(molid)
                else:
                    # The record in cache is obsolete
                    del self._names[key]

            # No luck so far, update the cache
            self._update()

            if key in self._names:
                # We found it after update. Do not check the existence again, we just updated the cache.
                return Molecule(self._names[key])
            else:
                raise ValueError("Molecule '%s' doesn't exist." % key)
        else:
            raise TypeError("%s indices must be integers or strings, not %s" % (type(self), type(key)))

    def __delitem__(self, key):
        """
        Deletes molecule specified by name or molid.

        If name is not unique, the molecule deleted is not defined.

        @type key: int or str
        """
        # Use __getitem__ to find out which molecule is to be deleted.
        molecule = self.__getitem__(key)
        # Clean the cache
        self._names.pop(molecule.name)
        # Delete molecule
        VMD.molecule.delete(molecule.molid)

    def __iter__(self):
        for molid in VMD.molecule.listall():
            yield Molecule(molid)

    def __contains__(self, molecule):
        return VMD.molecule.exists(molecule.molid)

    def _get_top(self):
        #XXX: Check if there is a molecule. `get_top` returns 0 even if there are no molecules.
        if not VMD.molecule.num():
            raise AttributeError("There are no molecules.")
        return Molecule(VMD.molecule.get_top())

    def _set_top(self, molecule):
        VMD.molecule.set_top(molecule.molid)

    top = property(_get_top, _set_top, doc="Top molecule")


MOLECULES = _MoleculeManager()
