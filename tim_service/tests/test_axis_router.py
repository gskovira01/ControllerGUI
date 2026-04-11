"""
TIM Service - Test Axis Router
===============================

Unit tests for the axis router command dispatcher.
"""

import pytest
from tim_axis_router import AxisRouter


class TestAxisRouter:
    """Test axis router command parsing and dispatch."""
    
    @pytest.fixture
    def router(self):
        """Create router for testing."""
        return AxisRouter(phantom_mode=True)
    
    def test_axis_extraction_sh_command(self, router):
        """Test axis extraction from SH (enable) command."""
        # "SH A" should extract axis 'A'
        axis = router._extract_axis("SH A")
        assert axis == "A"
    
    def test_axis_extraction_pa_command(self, router):
        """Test axis extraction from PA (absolute move) command."""
        # "PA A=45" should extract axis 'A'
        axis = router._extract_axis("PA A=45")
        assert axis == "A"
    
    def test_axis_extraction_mg_query(self, router):
        """Test axis extraction from MG (query) command."""
        # "MG _RPA" should extract axis 'A'
        axis = router._extract_axis("MG _RPA")
        assert axis == "A"
    
    def test_dispatch_enable_command(self, router):
        """Test dispatch of enable command."""
        response = router.dispatch("SH A")
        assert response == "1"  # Success
    
    def test_dispatch_disable_command(self, router):
        """Test dispatch of disable command."""
        response = router.dispatch("MO A")
        assert response == "0"  # Disabled
    
    def test_dispatch_absolute_move(self, router):
        """Test dispatch of absolute move command."""
        response = router.dispatch("PA A=45")
        assert response == "1"  # Success
    
    def test_dispatch_relative_move(self, router):
        """Test dispatch of relative move command."""
        response = router.dispatch("PR A=10")
        assert response == "1"  # Success
    
    def test_dispatch_set_speed(self, router):
        """Test dispatch of speed command."""
        response = router.dispatch("SP A=100")
        assert response == "1"  # Success
    
    def test_dispatch_clearcore_enable(self, router):
        """Test dispatch of ClearCore enable (axis E)."""
        response = router.dispatch("SH E")
        assert response == "1"  # Success
    
    def test_dispatch_clearcore_absolute_move(self, router):
        """Test dispatch of ClearCore absolute move."""
        response = router.dispatch("PA E=30")
        assert response == "1"  # Success


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
