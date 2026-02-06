//
// Compatibility wrapper for FilamentHubPanel refactoring
// This implementation file redirects to the new modular FilamentHub implementation
//
// All functionality has been moved to:
// - FilamentHub/FilamentHubPanel.cpp (UI layer)
// - FilamentHub/AuthManager.cpp (token management)
// - FilamentHub/SyncCoordinator.cpp (sync orchestration)
// - FilamentHub/PresetImporter.cpp (preset import logic)
//
// This file exists only for backward compatibility during the refactoring transition.
// It can be removed after all references to the old path are updated.
//

#include "FilamentHubPanel.hpp"

// No implementation needed - all functionality is in the new modules
// The header file re-exports the FilamentHubPanel class from FilamentHub/FilamentHubPanel.hpp
