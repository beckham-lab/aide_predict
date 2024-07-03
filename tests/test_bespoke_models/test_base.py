# tests/test_bespoke_models/test_base.py
'''
* Author: Evan Komp
* Created: 7/3/2024
* Company: National Renewable Energy Lab, Bioeneergy Science and Technology
* License: MIT
'''
import pytest
import os
import tempfile
import numpy as np
from unittest.mock import patch, MagicMock

from aide_predict.utils.data_structures import (
    ProteinSequence, ProteinSequences,
)
from aide_predict.bespoke_models.base import (
    ProteinModelWrapper, RequiresMSAMixin, RequiresFixedLengthMixin,
    CanRegressMixin, RequiresWTDuringInferenceMixin, PositionSpecificMixin
)


class TestProteinModelWrapper:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.temp_dir = tempfile.mkdtemp()
        self.model = ProteinModelWrapper(metadata_folder=self.temp_dir)
        yield
        import shutil
        shutil.rmtree(self.temp_dir)

    def test_init(self):
        assert os.path.exists(self.temp_dir)
        assert self.model.wt is None

    def test_wt_setter(self):
        self.model.wt = "ACDEFGHIKLMNPQRSTVWY"
        assert isinstance(self.model.wt, ProteinSequence)
        
        with pytest.raises(ValueError):
            self.model.wt = "ACDE-FGHIKLMNPQRSTVWY"

    def test_validate_input(self):
        input_list = ["ACDE", "FGHI"]
        result = self.model._validate_input(input_list)
        assert isinstance(result, ProteinSequences)

    def test_assert_aligned(self):
        mock_sequences = MagicMock()
        mock_sequences.aligned = False
        self.model._requires_msa_for_fit = True
        with pytest.raises(ValueError):
            self.model._assert_aligned(mock_sequences)

    def test_assert_fixed_length(self):
        mock_sequences = MagicMock()
        mock_sequences.fixed_length = False
        self.model._requires_fixed_length = True
        with pytest.raises(ValueError):
            self.model._assert_fixed_length(mock_sequences)

    def test_enforce_aligned(self):
        mock_sequences = MagicMock()
        mock_sequences.aligned = False
        mock_sequences.align_all.return_value = "aligned_sequences"
        result = self.model._enforce_aligned(mock_sequences)
        assert result == "aligned_sequences"

    def test_abstract_methods(self):
        with pytest.raises(NotImplementedError):
            self.model._fit(None)
        with pytest.raises(NotImplementedError):
            self.model._transform(None)
        with pytest.raises(NotImplementedError):
            self.model._partial_fit(None)

    @patch('aide_predict.bespoke_models.base.ProteinModelWrapper._fit')
    @patch('aide_predict.bespoke_models.base.ProteinModelWrapper._validate_input')
    @patch('aide_predict.bespoke_models.base.ProteinModelWrapper._assert_aligned')
    def test_fit(self, mock_assert_aligned, mock_validate_input, mock_fit):
        mock_validate_input.return_value = MagicMock()
        self.model.fit(["ACDE", "FGHI"])
        mock_fit.assert_called_once()

    @patch('aide_predict.bespoke_models.base.ProteinModelWrapper._transform')
    @patch('aide_predict.bespoke_models.base.ProteinModelWrapper._validate_input')
    def test_transform(self, mock_validate_input, mock_transform):
        mock_validate_input.return_value = MagicMock()
        mock_transform.return_value = np.array([1, 2, 3])
        self.model.fitted_ = True  # Mock fitted state
        result = self.model.transform(["ACDE", "FGHI"])
        np.testing.assert_array_equal(result, np.array([1, 2, 3]))

    def test_predict_not_regressor(self):
        with pytest.raises(ValueError):
            self.model.predict(["ACDE", "FGHI"])

    def test_get_set_params(self):
        params = self.model.get_params()
        assert 'metadata_folder' in params
        assert 'wt' in params

        new_params = {'metadata_folder': '/new/path', 'wt': 'ACDE'}
        self.model.set_params(**new_params)
        assert self.model.metadata_folder == '/new/path'
        assert str(self.model.wt) == 'ACDE'

    def test_get_feature_names_out(self):
        self.model.fitted_ = True  # Mock fitted state
        feature_names = self.model.get_feature_names_out()
        assert feature_names == ['ProteinModelWrapper']

    @pytest.mark.parametrize("mixin_class,attribute,expected", [
        (RequiresMSAMixin, 'requires_msa_for_fit', True),
        (RequiresFixedLengthMixin, 'requires_fixed_length', True),
        (CanRegressMixin, 'can_regress', True),
        (RequiresWTDuringInferenceMixin, 'requires_wt_during_inference', True),
    ])
    def test_mixins(self, mixin_class, attribute, expected):
        class TestModel(mixin_class, ProteinModelWrapper):
            pass
        tempdir = tempfile.mkdtemp()
        model = TestModel(metadata_folder=tempdir)
        assert getattr(model, attribute) == expected

    def test_position_specific_mixin(self):
        class TestModel(PositionSpecificMixin, ProteinModelWrapper):
            def __init__(self, *args, **kwargs):
                self.positions = [1, 2, 3]
                self.pool = False
                super().__init__(*args, **kwargs)
        tempdir = tempfile.mkdtemp()
        model = TestModel(metadata_folder=tempdir)
        assert model.per_position_capable

        with patch.object(ProteinModelWrapper, 'transform') as mock_transform:
            mock_transform.return_value = np.array([[1, 2, 3]])
            result = model.transform(["ACDE"])
            np.testing.assert_array_equal(result, np.array([[1, 2, 3]]))

        with patch.object(ProteinModelWrapper, 'transform') as mock_transform:
            mock_transform.return_value = np.array([[1, 2]])
            with pytest.raises(ValueError):
                model.transform(["ACDE"])

        model.fitted_ = True  # Mock fitted state
        feature_names = model.get_feature_names_out()
        assert feature_names == ['TestModel_1', 'TestModel_2', 'TestModel_3']