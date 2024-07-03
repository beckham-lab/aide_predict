# aide_predict/data_structures.py
'''
* Author: Evan Komp
* Created: 6/21/2024
* Company: Bottle Institute @ National Renewable Energy Lab, Bioeneergy Science and Technology
* License: MIT

Base data structures for the AIDE Predict package Where they do not exist in sklearn.
'''
from collections import UserList
import os
import warnings
import numpy as np

from aide_predict.io.bio_files import read_fasta, write_fasta
from aide_predict.utils.alignment_calls import sw_global_pairwise, mafft_align

from typing import List, Optional, Union, Iterator, Dict, Iterable, Any

from .constants import AA_SINGLE, GAP_CHARACTERS, NON_CONONICAL_AA_SINGLE


############################################
# A class to store a single protein character and sequence
# They are treated like strings, eg you can do all that you expect from an AA string
# but also stores id, structure, and has additional methods to check for gaps, non-canonical AAs, etc.
############################################

class ProteinCharacter(str):
    """
    Represents a single character in a protein sequence.

    This class inherits from UserString and provides additional properties
    to check the nature of the amino acid character.
    """

    def __new__(cls, seq: str):
        """
        Create a new ProteinCharacter object.

        Args:
            seq (str): A single character representing an amino acid or gap.

        Returns:
            ProteinCharacter: The new ProteinCharacter object.
        """
        obj =  str.__new__(cls, seq)
        if len(obj) != 1:
            raise ValueError("ProteinCharacter must be initialized with a single character")
        if obj.upper() not in AA_SINGLE.union(GAP_CHARACTERS).union(NON_CONONICAL_AA_SINGLE):
            raise ValueError(f"Invalid character {obj} for protein sequence.")
        return obj

    @property
    def is_gap(self) -> bool:
        """Check if the character represents a gap in the sequence."""
        return self in GAP_CHARACTERS

    @property
    def is_non_canonical(self) -> bool:
        """Check if the character represents a non-canonical amino acid."""
        return self in NON_CONONICAL_AA_SINGLE
    
    @property
    def is_not_focus(self) -> bool:
        """
        Check if the character is not in focus.
        
        A character is considered not in focus if it's a gap or a lowercase letter.
        """
        return self.is_gap or self.islower()

    def __repr__(self) -> str:
        """Return a string representation of the ProteinCharacter."""
        return f"ProteinCharacter('{self}')"


class ProteinSequence(str):
    """
    Represents a protein sequence.

    This class inherits from UserString and provides additional methods and properties
    for analyzing and manipulating protein sequences.
    """
    def __new__(cls, seq: str, id: Optional[str] = None, structure: Optional[str] = None):
        """
        Create a new ProteinSequence object.

        Args:
            seq (str): The amino acid sequence.
            id (Optional[str]): An identifier for the sequence.
            structure (Optional[str]): The structure of the protein sequence.

        Returns:
            ProteinSequence: The new ProteinSequence object.
        """
        obj = str.__new__(cls, seq)
        obj._characters: List[ProteinCharacter] = [ProteinCharacter(c) for c in seq]
        obj._id: Optional[str] = None
        obj._structure: Optional[str] = None

        if id is not None:
            obj.id = id
        if structure is not None:
            obj.structure = structure

        return obj

    @property
    def id(self) -> Optional[str]:
        """Get the identifier of the sequence."""
        return self._id
    
    @property
    def structure(self) -> Optional[str]:
        """Get the structure of the sequence."""
        return self._structure
    
    def __hash__(self) -> int:
        """Compute a hash value for the ProteinSequence."""
        return hash((tuple(self._characters), self._id))
    
    def __eq__(self, other: object) -> bool:
        """Check if two ProteinSequence objects are equal."""
        return hash(self) == hash(other)
    
    def __ne__(self, other: object) -> bool:
        """Check if two ProteinSequence objects are not equal."""
        return not self == other

    def __repr__(self) -> str:
        """Return a string representation of the ProteinSequence."""
        return f"ProteinSequence(id={self._id!r}, seq='{self[:20]}{'...' if len(self) > 20 else ''}')"

    @property
    def has_gaps(self) -> bool:
        """Check if the sequence contains any gaps."""
        return any(c.is_gap for c in self._characters)
    
    @property
    def has_non_canonical(self) -> bool:
        """Check if the sequence contains any non-canonical amino acids."""
        return any(c.is_non_canonical for c in self._characters)

    def with_no_gaps(self) -> 'ProteinSequence':
        """Return a new ProteinSequence with all gaps removed."""
        return ProteinSequence("".join(c for c in self if c not in GAP_CHARACTERS),
                               id=self._id, structure=self._structure)
    
    @property
    def as_array(self) -> np.ndarray:
        """Convert the sequence to a numpy array of characters."""
        return np.array([c for c in self._characters]).reshape(1,-1)

    @property
    def num_gaps(self) -> int:
        """Get the number of gaps in the sequence."""
        return sum(c.is_gap for c in self._characters)
    
    @property
    def base_length(self) -> int:
        """Get the length of the sequence excluding gaps."""
        return len(self) - self.num_gaps

    def mutate(self, position: int, new_character: str) -> 'ProteinSequence':
        """
        Create a new ProteinSequence with a mutation at the specified position.

        Args:
            position (int): The position to mutate.
            new_character (str): The new character to insert at the position.

        Returns:
            ProteinSequence: A new ProteinSequence with the mutation applied.
        """
        if position < 0 or position >= len(self):
            raise ValueError("Position out of range")
        new_seq = self[:position] + new_character + self[position+1:]
        return ProteinSequence(new_seq, structure=self._structure)  # Note: id is not passed to indicate mutation

    def mutated_positions(self, other: Union[str, 'ProteinSequence']) -> List[int]:
        """
        Find positions where this sequence differs from another.

        Args:
            other (Union[str, ProteinSequence]): The sequence to compare against.

        Returns:
            List[int]: A list of positions where the sequences differ.
        """
        other_seq = other if isinstance(other, ProteinSequence) else other
        return [i for i, (a, b) in enumerate(zip(self, other_seq)) if a != b]

    def get_protein_character(self, position: int) -> ProteinCharacter:
        """
        Get the ProteinCharacter at the specified position.

        Args:
            position (int): The position to get the character from.

        Returns:
            ProteinCharacter: The character at the specified position.
        """
        if position < 0 or position >= len(self):
            raise IndexError("Position out of range")
        return self._characters[position]

    def slice_as_protein_sequence(self, start: int, end: int) -> 'ProteinSequence':
        """
        Create a new ProteinSequence from a slice of this sequence.

        Args:
            start (int): The start position of the slice.
            end (int): The end position of the slice.

        Returns:
            ProteinSequence: A new ProteinSequence containing the specified slice.
        """
        return ProteinSequence(self[start:end], id=self._id, structure=self._structure)

    def iter_protein_characters(self) -> Iterator[ProteinCharacter]:
        """
        Iterate over the ProteinCharacters in the sequence.

        Returns:
            Iterator[ProteinCharacter]: An iterator over the ProteinCharacters.
        """
        return iter(self._characters)

    @property
    def id(self) -> Optional[str]:
        """Get the identifier of the sequence."""
        return self._id
    
    @id.setter
    def id(self, new_id: str) -> None:
        """Set the identifier of the sequence."""
        self._id = new_id

    @property
    def structure(self) -> Optional[str]:
        """Get the structure of the sequence."""
        return self._structure
    
    @structure.setter
    def structure(self, new_structure: str) -> None:
        """Set the structure of the sequence."""
        if os.path.exists(new_structure):
            pass
        else:
            raise ValueError(f"Structure file {new_structure} does not exist.")
        self._structure = new_structure
    
    def align(self, other: 'ProteinSequence') -> 'ProteinSequence':
        """
        Align this sequence with another using global pairwise alignment.

        Args:
            other (ProteinSequence): The sequence to align with.

        Returns:
            ProteinSequence: The aligned sequence.
        """
        base_self = self.with_no_gaps()
        base_other = other.with_no_gaps()

        aligned_seq, aligned_other = sw_global_pairwise(base_self, base_other)
        return aligned_seq, aligned_other

############################################
# A class to store multiple ProteinSequence objects
# Think of this as a dataset of protein sequences, no labels eg. the X for proteins
# Useful additional functionalities built in: alignment, fasta read/write, testing for alignment, gaps,
# fixed length, etc.
############################################

class ProteinSequences(UserList):
    """
    A collection of ProteinSequence objects with additional functionality.
    
    Attributes:
        aligned (bool): True if all sequences have the same length, False otherwise.
        fixed_length (bool): True if all sequences have the same base length, False otherwise.
        width (Optional[int]): The length of the sequences if aligned, None otherwise.
        has_gaps (bool): True if any sequence has gaps, False otherwise.
        mutated_positions (Optional[List[int]]): List of mutated positions if aligned, None otherwise.

    Methods:
        to_dict: Convert ProteinSequences to a dictionary.
        to_fasta: Write sequences to a FASTA file.
        from_fasta: Create a ProteinSequences object from a FASTA file.
    """

    def __init__(self, sequences: List[ProteinSequence]):
        """
        Initialize a ProteinSequences object.

        Args:
            sequences (List[ProteinSequence]): A list of ProteinSequence objects.
        """
        super().__init__(sequences)

    @property
    def aligned(self) -> bool:
        """
        Check if all sequences are of equal length (including gaps).

        Returns:
            bool: True if all sequences have the same length, False otherwise.
        """
        return len(set(len(seq) for seq in self)) == 1

    @property
    def fixed_length(self) -> bool:
        """
        Check if all contained sequences have the same base length (excluding gaps).

        Returns:
            bool: True if all sequences have the same base length, False otherwise.
        """
        return len(set(seq.base_length for seq in self)) == 1

    @property
    def width(self) -> Optional[int]:
        """
        Get the length of the sequences if aligned.

        Returns:
            Optional[int]: The length of the sequences if aligned, None otherwise.
        """
        return len(self[0]) if self.aligned else None

    @property
    def has_gaps(self) -> bool:
        """
        Check if any sequences have gaps.

        Returns:
            bool: True if any sequence has gaps, False otherwise.
        """
        return any(seq.has_gaps for seq in self)

    @property
    def mutated_positions(self) -> Optional[List[int]]:
        """
        List columns that have more than one character, assuming sequences are aligned.

        Returns:
            Optional[List[int]]: List of mutated positions if aligned, None otherwise.
        """
        if not self.aligned:
            warnings.warn("Sequences are not aligned. Cannot determine mutated positions.")
            return None

        if not self:  # If the list is empty
            return []

        mutated = []
        seq_length = len(self[0])
        for i in range(seq_length):
            chars = set(seq.get_protein_character(i) for seq in self)
            if len(chars) > 1:
                mutated.append(i)
        return mutated

    def to_dict(self) -> Dict[str, str]:
        """
        Convert ProteinSequences to a dictionary.

        Returns:
            Dict[str, str]: A dictionary with sequence IDs as keys and sequences as values.
        """
        return {seq.id or hash(seq): str(seq) for seq in self}

    def to_fasta(self, output_path: str):
        """
        Write sequences to a FASTA file.

        Args:
            output_path (str): The path to the output FASTA file.
        """

        with open(output_path, 'w') as f:
            write_fasta(((seq.id or hash(seq), str(seq)) for seq in self), f)

    @classmethod
    def from_fasta(cls, input_path: str) -> 'ProteinSequences':
        """
        Create a ProteinSequences object from a FASTA file.

        Args:
            input_path (str): The path to the input FASTA file.

        Returns:
            ProteinSequences: A new ProteinSequences object containing the sequences from the FASTA file.
        """

        sequences = []
        with open(input_path, 'r') as f:
            for id, seq in read_fasta(f):
                sequences.append(ProteinSequence(seq, id=id))
        return cls(sequences)

    def __repr__(self) -> str:
        """
        Return a string representation of the ProteinSequences object.

        Returns:
            str: A string representation of the object.
        """
        return f"ProteinSequences(count={len(self)}, aligned={self.aligned}, fixed_length={self.fixed_length})"
    
    def to_on_file(self, output_path: str) -> None:
        """
        Write sequences to a FASTA file.

        Args:
            output_path (str): The path to the output FASTA file.
        """
        with open(output_path, 'w') as f:
            write_fasta(((seq.id or hash(seq), str(seq)) for seq in self), f)
        return ProteinSequencesOnFile(output_path)
    
    def as_array(self) -> np.ndarray:
        """Convert the sequence to a numpy array of characters."""
        if not self.aligned:
            raise ValueError("Sequences must be aligned to convert to array.")
        return np.vstack([seq.as_array for seq in self])


    def iter_batches(self, batch_size: int) -> Iterable['ProteinSequences']:
        """
        Iterate over batches of sequences.

        Args:
            batch_size (int): The size of each batch.

        Yields:
            ProteinSequences: A batch of sequences.
        """
        for i in range(0, len(self), batch_size):
            yield ProteinSequences(self[i:i+batch_size])


    def align_all(self, output_fasta: Optional[str] = None) -> Union['ProteinSequences', 'ProteinSequencesOnFile']:
        """
        Align the sequences within this ProteinSequences object using MAFFT.

        Args:
            output_fasta (Optional[str]): Path to save the alignment. If None, a temporary file is used.

        Returns:
            Union[ProteinSequences, ProteinSequencesOnFile]: The aligned sequences, either in memory or on file 
            depending on output_fasta.

        Raises:
            ValueError: If the sequences already contain gaps.
            RuntimeError: If MAFFT alignment fails.
            FileNotFoundError: If MAFFT is not installed or not in PATH.
        """
        if self.has_gaps:
            raise ValueError("Sequences already contain gaps. Cannot perform alignment on gapped sequences.")

        return mafft_align(self, output_fasta=output_fasta)
    
    def align_to(self, existing_alignment: Union['ProteinSequences', 'ProteinSequencesOnFile'], 
                 realign: bool = False, 
                 output_fasta: Optional[str] = None) -> Union['ProteinSequences', 'ProteinSequencesOnFile']:
        """
        Align this ProteinSequences object to an existing alignment using MAFFT.

        Args:
            existing_alignment (Union[ProteinSequences, ProteinSequencesOnFile]): The existing alignment to align to.
            realign (bool): If True, realign all sequences from scratch. If False, add new sequences to existing alignment.
            output_fasta (Optional[str]): Path to save the alignment. If None, a temporary file is used.

        Returns:
            Union[ProteinSequences, ProteinSequencesOnFile]: The aligned sequences, either in memory or on file 
            depending on output_fasta.

        Raises:
            ValueError: If the sequences already contain gaps or if the existing alignment is not aligned.
            RuntimeError: If MAFFT alignment fails.
            FileNotFoundError: If MAFFT is not installed or not in PATH.
        """
        if self.has_gaps:
            raise ValueError("Sequences already contain gaps. Cannot perform alignment on gapped sequences.")

        if not existing_alignment.aligned:
            raise ValueError("Existing alignment must be aligned.")

        return mafft_align(self, existing_alignment=existing_alignment, realign=realign, output_fasta=output_fasta)
    
    def with_no_gaps(self) -> 'ProteinSequences':
        """Return a new ProteinSequences with all gaps removed."""
        return ProteinSequences([seq.with_no_gaps() for seq in self])

    def get_alignment_mapping(self) -> Dict[int, List[Optional[int]]]:
        """
        Create a mapping of original sequence positions to aligned positions for each sequence.

        Returns:
            Dict[int, List[Optional[int]]]: A dictionary where keys are sequence indices and values are
            lists of integers. Each integer represents the position in the aligned sequence
            corresponding to the original sequence position. Eg. [0,1,2,5,6,7] incidates that the 
            there is a gap between amino acid 2 and 3, and 3 is in position 5 in the aligned sequence.

        Raises:
            ValueError: If the sequences are not aligned.
        """
        if not self.aligned:
            raise ValueError("Sequences must be aligned to create an alignment mapping.")

        mapping = {}
        for i, seq in enumerate(self):
            seq_mapping = []
            original_pos = 0
            for aligned_pos, char in enumerate(seq.iter_protein_characters()):
                if not char.is_gap:
                    seq_mapping.append(aligned_pos)
                    original_pos += 1
                else:
                    pass
            mapping[i] = seq_mapping

        return mapping

    def apply_alignment_mapping(self, mapping: Dict[int, List[Optional[int]]]) -> 'ProteinSequences':
        """
        Apply an alignment mapping to the current sequences.

        Args:
            mapping (Dict[int, List[Optional[int]]]): The alignment mapping to apply.

        Returns:
            ProteinSequences: A new ProteinSequences object with aligned sequences.

        Raises:
            ValueError: If a sequence index is not found in the mapping or if the mapping is invalid.
        """
        if self.has_gaps:
            raise ValueError("Sequences already contain gaps. Cannot apply alignment mapping to gapped sequences.")

        aligned_sequences = []
        for i, seq in enumerate(self):
            if i not in mapping:
                raise ValueError(f"Sequence index {i} not found in the alignment mapping.")

            seq_mapping = mapping[i]
            aligned_seq = ['-'] * (max(filter(None, seq_mapping)) + 1)
            for original_pos, aligned_pos in enumerate(seq_mapping):
                if original_pos >= len(seq):
                    raise ValueError(f"Invalid mapping for sequence at index {i}: original position {original_pos} out of range.")
                aligned_seq[aligned_pos] = seq[original_pos]

            aligned_sequences.append(ProteinSequence(''.join(aligned_seq), id=seq.id, structure=seq.structure))

        return ProteinSequences(aligned_sequences)
    
############################################
# A class with the same API as ProteinSequences but on file instead of in memory
############################################

class ProteinSequencesOnFile(ProteinSequences):
    """
    A memory-efficient representation of protein sequences stored in a FASTA file.
    
    This class maintains the same API as ProteinSequences but avoids loading all sequences
    into memory at once. It creates an index of the FASTA file for efficient access to
    individual sequences and precomputes some global properties for quick access.

    Attributes:
        aligned (bool): True if all sequences have the same length, False otherwise.
        fixed_length (bool): True if all sequences have the same base length, False otherwise.
        width (Optional[int]): The length of the sequences if aligned, None otherwise.
        has_gaps (bool): True if any sequence has gaps, False otherwise.
        mutated_positions (Optional[List[int]]): List of mutated positions if aligned, None otherwise.

    Methods:
        to_dict: Convert ProteinSequences to a dictionary.
        to_fasta: Write sequences to a FASTA file.
        from_fasta: Create a ProteinSequences object from a FASTA file.
    """

    def __init__(self, file_path: str):
        """
        Initialize a ProteinSequencesOnFile object.

        Args:
            file_path (str): Path to the FASTA file containing protein sequences.
        """
        super().__init__([])  # Initialize with an empty list
        self.file_path: str = file_path
        self._index: Dict[str, Dict[str, Any]] = {}
        self._create_index()
        self._compute_global_properties()

    def _create_index(self) -> None:
        """
        Create an index of sequences in the FASTA file for efficient access.

        This method reads through the FASTA file once, creating an index with
        information about each sequence's position, length, and other properties.
        """
        with open(self.file_path, 'r') as f:
            current_id: Optional[str] = None
            seq_start: Optional[int] = None
            seq_length: int = 0
            has_gaps: bool = False
            base_length: int = 0
            file_pos: int = 0

            for line in f:
                if line.startswith('>'):
                    if current_id is not None:
                        self._index[current_id] = {
                            'start': seq_start,
                            'length': seq_length,
                            'has_gaps': has_gaps,
                            'base_length': base_length
                        }
                    current_id = line[1:].strip().split()[0]
                    seq_start = file_pos + len(line)
                    seq_length = 0
                    has_gaps = False
                    base_length = 0
                else:
                    seq = line.strip()
                    seq_length += len(seq)
                    has_gaps = has_gaps or ('-' in seq)
                    base_length += len(seq.replace('-', ''))
                file_pos += len(line)

            if current_id is not None:
                self._index[current_id] = {
                    'start': seq_start,
                    'length': seq_length,
                    'has_gaps': has_gaps,
                    'base_length': base_length
                }

    def _compute_global_properties(self) -> None:
        """
        Compute global properties based on the index.

        This method calculates properties like alignment status, fixed length,
        width, and presence of gaps across all sequences.
        """
        lengths: set = set(info['length'] for info in self._index.values())
        base_lengths: set = set(info['base_length'] for info in self._index.values())
        
        self._aligned: bool = len(lengths) == 1
        self._fixed_length: bool = len(base_lengths) == 1
        self._width: Optional[int] = next(iter(lengths)) if self._aligned else None
        self._has_gaps: bool = any(info['has_gaps'] for info in self._index.values())

    def __len__(self) -> int:
        """
        Return the number of sequences in the file.

        Returns:
            int: The number of sequences.
        """
        return len(self._index)

    def __getitem__(self, index: Union[int, str]) -> ProteinSequence:
        """
        Get a ProteinSequence by index or ID.

        Args:
            index (Union[int, str]): Index or ID of the sequence.

        Returns:
            ProteinSequence: The requested protein sequence.

        Raises:
            IndexError: If the index is out of range.
            KeyError: If the ID is not found.
        """
        if isinstance(index, int):
            if index < 0 or index >= len(self):
                raise IndexError("Index out of range")
            id = list(self._index.keys())[index]
        else:
            id = index

        if id not in self._index:
            raise KeyError(f"Sequence ID '{id}' not found")

        info = self._index[id]
        with open(self.file_path, 'r') as f:
            f.seek(info['start'])
            sequence = ''.join(f.read(info['length']).split())
        return ProteinSequence(sequence, id=id)

    def __iter__(self) -> Iterable[ProteinSequence]:
        """
        Iterate over all sequences in the file.

        Yields:
            ProteinSequence: Each protein sequence in the file.
        """
        with open(self.file_path, 'r') as f:
            for id, seq in read_fasta(f):
                yield ProteinSequence(seq, id=id)

    @property
    def aligned(self) -> bool:
        """
        Check if all sequences are of equal length (including gaps).

        Returns:
            bool: True if all sequences have the same length, False otherwise.
        """
        return self._aligned

    @property
    def fixed_length(self) -> bool:
        """
        Check if all contained sequences have the same base length (excluding gaps).

        Returns:
            bool: True if all sequences have the same base length, False otherwise.
        """
        return self._fixed_length

    @property
    def width(self) -> Optional[int]:
        """
        Get the length of the sequences if aligned.

        Returns:
            Optional[int]: The length of the sequences if aligned, None otherwise.
        """
        return self._width

    @property
    def has_gaps(self) -> bool:
        """
        Check if any sequences have gaps.

        Returns:
            bool: True if any sequence has gaps, False otherwise.
        """
        return self._has_gaps

    @property
    def mutated_positions(self) -> Optional[List[int]]:
        """
        List columns that have more than one character, assuming sequences are aligned.

        Returns:
            Optional[List[int]]: List of mutated positions if aligned, None otherwise.
        """
        if not self.aligned:
            return None
        positions: List[set] = [set() for _ in range(self.width)]
        for seq in self:
            for i, char in enumerate(str(seq)):
                positions[i].add(char)
        return [i for i, chars in enumerate(positions) if len(chars) > 1]

    def to_dict(self) -> Dict[str, str]:
        """
        Convert sequences to a dictionary.

        Returns:
            Dict[str, str]: A dictionary with sequence IDs as keys and sequences as values.
        """
        return {id: str(self[id]) for id in self._index}

    def to_fasta(self, output_path: str) -> None:
        """
        Write sequences to a FASTA file.

        Args:
            output_path (str): The path to the output FASTA file.
        """
        with open(output_path, 'w') as f:
            write_fasta(((id, str(self[id])) for id in self._index), f)

    @classmethod
    def from_fasta(cls, input_path: str) -> 'ProteinSequencesOnFile':
        """
        Create a ProteinSequencesOnFile object from a FASTA file.

        Args:
            input_path (str): The path to the input FASTA file.

        Returns:
            ProteinSequencesOnFile: A new ProteinSequencesOnFile object.
        """
        return cls(input_path)

    def __repr__(self) -> str:
        """
        Return a string representation of the ProteinSequencesOnFile object.

        Returns:
            str: A string representation of the object.
        """
        return f"ProteinSequencesOnFile(file='{self.file_path}', count={len(self)}, aligned={self.aligned}, fixed_length={self.fixed_length})"
    
    def to_memory(self) -> ProteinSequences:
        """
        Load all sequences into memory as a ProteinSequences object.

        Returns:
            ProteinSequences: A new ProteinSequences object containing all sequences.
        """
        return ProteinSequences(list(self))
    
    def iter_batches(self, batch_size: int) -> Iterable[ProteinSequences]:
        """
        Iterate over batches of sequences.

        Args:
            batch_size (int): The size of each batch.

        Yields:
            ProteinSequences: A batch of sequences.
        """
        for i in range(0, len(self), batch_size):
            yield ProteinSequences([self[id] for id in list(self._index.keys())[i:i+batch_size]])
    

    