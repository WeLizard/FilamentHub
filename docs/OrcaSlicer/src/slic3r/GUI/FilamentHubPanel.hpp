#ifndef slic3r_GUI_FilamentHubPanel_Legacy_hpp_
#define slic3r_GUI_FilamentHubPanel_Legacy_hpp_

//
// Compatibility wrapper for FilamentHubPanel refactoring
// This header redirects to the new modular FilamentHub implementation
//

// Include new modular headers
#include "FilamentHub/FilamentHubPanel.hpp"
#include "FilamentHub/AuthManager.hpp"
#include "FilamentHub/SyncCoordinator.hpp"
#include "FilamentHub/PresetImporter.hpp"

// Forward declarations for backward compatibility
namespace Slic3r {
namespace GUI {

// The FilamentHubPanel class is now defined in FilamentHub/FilamentHubPanel.hpp
// This file exists only for backward compatibility during the refactoring transition

// Re-export the class from the FilamentHub namespace
using FilamentHubPanel = ::Slic3r::GUI::FilamentHubPanel;

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FilamentHubPanel_Legacy_hpp_
