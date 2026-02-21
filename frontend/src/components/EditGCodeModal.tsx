import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Search, ChevronRight, ChevronDown } from 'lucide-react';

interface Placeholder {
  key: string;
  name: string;
  description?: string;
  type: 'scalar' | 'vector' | 'filament_vector';
  category: string;
  subcategory?: string;
}

interface Category {
  id: string;
  name: string;
  icon?: string;
  placeholders: Placeholder[];
  subcategories?: Record<string, Placeholder[]>;
}

interface EditGCodeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onInsert: (placeholderText: string) => void;
  title: string;
  gcodeType?: 'filament_start_gcode' | 'filament_end_gcode';
}

// Базовые плейсхолдеры из OrcaSlicer (из PrintConfig.cpp и EditGCodeDialog.cpp)
const PLACEHOLDERS: Placeholder[] = [
  // Slicing State - Read Only
  { key: 'zhop', name: 'zhop', description: 'Current Z-hop present at the beginning of the custom G-code block', type: 'scalar', category: '[Global] Slicing State', subcategory: 'Read Only' },
  
  // Slicing State - Read Write
  { key: 'position', name: 'position', description: 'Position of the extruder at the beginning of the custom G-code block (vector [x, y, z, e])', type: 'vector', category: '[Global] Slicing State', subcategory: 'Read Write' },
  { key: 'e_retracted', name: 'e_retracted', description: 'Retraction state at the beginning of the custom G-code block (vector)', type: 'vector', category: '[Global] Slicing State', subcategory: 'Read Write' },
  { key: 'e_restart_extra', name: 'e_restart_extra', description: 'Currently planned extra extruder priming after de-retraction (vector)', type: 'vector', category: '[Global] Slicing State', subcategory: 'Read Write' },
  { key: 'e_position', name: 'e_position', description: 'Current position of the extruder axis (absolute, vector)', type: 'vector', category: '[Global] Slicing State', subcategory: 'Read Write' },
  
  // Slicing State - Other
  { key: 'current_extruder', name: 'current_extruder', description: 'Zero-based index of currently used extruder', type: 'scalar', category: 'Slicing State' },
  { key: 'current_object_idx', name: 'current_object_idx', description: 'Zero-based index of currently printed object (sequential printing)', type: 'scalar', category: 'Slicing State' },
  { key: 'has_wipe_tower', name: 'has_wipe_tower', description: 'Whether or not wipe tower is being generated in the print', type: 'scalar', category: 'Slicing State' },
  { key: 'initial_extruder', name: 'initial_extruder', description: 'Zero-based index of the first extruder used in the print (same as initial_tool)', type: 'scalar', category: 'Slicing State' },
  { key: 'initial_tool', name: 'initial_tool', description: 'Zero-based index of the first extruder used in the print (same as initial_extruder)', type: 'scalar', category: 'Slicing State' },
  { key: 'is_extruder_used', name: 'is_extruder_used', description: 'Vector of booleans stating whether a given extruder is used in the print', type: 'vector', category: 'Slicing State' },
  { key: 'has_single_extruder_multi_material_priming', name: 'has_single_extruder_multi_material_priming', description: 'Are the extra multi-material priming regions used in this print?', type: 'scalar', category: 'Slicing State' },
  { key: 'initial_no_support_extruder', name: 'initial_no_support_extruder', description: 'Zero-based index of the first extruder used for printing without support', type: 'scalar', category: 'Slicing State' },
  { key: 'in_head_wrap_detect_zone', name: 'in_head_wrap_detect_zone', description: 'Indicates if the first layer overlaps with the head wrap zone', type: 'scalar', category: 'Slicing State' },
  
  // Print Statistics
  { key: 'extruded_volume', name: 'extruded_volume', description: 'Total filament volume extruded per extruder during the entire print (vector)', type: 'vector', category: 'Print Statistics' },
  { key: 'total_toolchanges', name: 'total_toolchanges', description: 'Number of tool changes during the print', type: 'scalar', category: 'Print Statistics' },
  { key: 'extruded_volume_total', name: 'extruded_volume_total', description: 'Total volume of filament used during the entire print', type: 'scalar', category: 'Print Statistics' },
  { key: 'extruded_weight', name: 'extruded_weight', description: 'Weight per extruder extruded during the entire print (vector)', type: 'vector', category: 'Print Statistics' },
  { key: 'extruded_weight_total', name: 'extruded_weight_total', description: 'Total weight of the print', type: 'scalar', category: 'Print Statistics' },
  { key: 'total_layer_count', name: 'total_layer_count', description: 'Number of layers in the entire print', type: 'scalar', category: 'Print Statistics' },
  
  // Objects Info
  { key: 'num_objects', name: 'num_objects', description: 'Total number of objects in the print', type: 'scalar', category: 'Objects Info' },
  { key: 'num_instances', name: 'num_instances', description: 'Total number of object instances in the print, summed over all objects', type: 'scalar', category: 'Objects Info' },
  { key: 'scale', name: 'scale', description: 'Scale per object (vector of strings, e.g. "x:100% y:50% z:100")', type: 'vector', category: 'Objects Info' },
  { key: 'input_filename_base', name: 'input_filename_base', description: 'Source filename of the first object, without extension', type: 'scalar', category: 'Objects Info' },
  { key: 'input_filename', name: 'input_filename', description: 'Source filename of the first object (full filename)', type: 'scalar', category: 'Objects Info' },
  { key: 'plate_name', name: 'plate_name', description: 'Name of the plate sliced', type: 'scalar', category: 'Objects Info' },
  
  // Dimensions
  { key: 'first_layer_print_convex_hull', name: 'first_layer_print_convex_hull', description: 'Vector of points of the first layer convex hull (format: "[x, y]")', type: 'vector', category: 'Dimensions' },
  { key: 'first_layer_print_min', name: 'first_layer_print_min', description: 'Bottom-left corner of first layer bounding box (vector [x, y])', type: 'vector', category: 'Dimensions' },
  { key: 'first_layer_print_max', name: 'first_layer_print_max', description: 'Top-right corner of first layer bounding box (vector [x, y])', type: 'vector', category: 'Dimensions' },
  { key: 'first_layer_print_size', name: 'first_layer_print_size', description: 'Size of the first layer bounding box (vector [x, y])', type: 'vector', category: 'Dimensions' },
  { key: 'print_bed_min', name: 'print_bed_min', description: 'Bottom-left corner of print bed bounding box (vector [x, y])', type: 'vector', category: 'Dimensions' },
  { key: 'print_bed_max', name: 'print_bed_max', description: 'Top-right corner of print bed bounding box (vector [x, y])', type: 'vector', category: 'Dimensions' },
  { key: 'print_bed_size', name: 'print_bed_size', description: 'Size of the print bed bounding box (vector [x, y])', type: 'vector', category: 'Dimensions' },
  { key: 'first_layer_center_no_wipe_tower', name: 'first_layer_center_no_wipe_tower', description: 'First layer center without wipe tower (vector [x, y])', type: 'vector', category: 'Dimensions' },
  { key: 'first_layer_height', name: 'first_layer_height', description: 'Height of the first layer', type: 'scalar', category: 'Dimensions' },
  
  // Temperatures
  { key: 'bed_temperature', name: 'bed_temperature', description: 'Vector of bed temperatures for each extruder/filament', type: 'vector', category: 'Temperatures' },
  { key: 'bed_temperature_initial_layer', name: 'bed_temperature_initial_layer', description: 'Vector of initial layer bed temperatures for each extruder/filament', type: 'vector', category: 'Temperatures' },
  { key: 'bed_temperature_initial_layer_single', name: 'bed_temperature_initial_layer_single', description: 'Initial layer bed temperature for the initial extruder', type: 'scalar', category: 'Temperatures' },
  { key: 'chamber_temperature', name: 'chamber_temperature', description: 'Vector of chamber temperatures for each extruder/filament', type: 'vector', category: 'Temperatures' },
  { key: 'overall_chamber_temperature', name: 'overall_chamber_temperature', description: 'Overall chamber temperature (maximum of any extruder/filament)', type: 'scalar', category: 'Temperatures' },
  { key: 'first_layer_bed_temperature', name: 'first_layer_bed_temperature', description: 'Vector of first layer bed temperatures for each extruder/filament', type: 'vector', category: 'Temperatures' },
  { key: 'first_layer_temperature', name: 'first_layer_temperature', description: 'Vector of first layer temperatures for each extruder/filament', type: 'vector', category: 'Temperatures' },
  
  // Timestamps
  { key: 'timestamp', name: 'timestamp', description: 'Current time in yyyyMMdd-hhmmss format', type: 'scalar', category: 'Timestamps' },
  { key: 'year', name: 'year', description: 'Current year', type: 'scalar', category: 'Timestamps' },
  { key: 'month', name: 'month', description: 'Current month', type: 'scalar', category: 'Timestamps' },
  { key: 'day', name: 'day', description: 'Current day', type: 'scalar', category: 'Timestamps' },
  { key: 'hour', name: 'hour', description: 'Current hour', type: 'scalar', category: 'Timestamps' },
  { key: 'minute', name: 'minute', description: 'Current minute', type: 'scalar', category: 'Timestamps' },
  { key: 'second', name: 'second', description: 'Current second', type: 'scalar', category: 'Timestamps' },
];

// Filament-specific placeholders
const FILAMENT_PLACEHOLDERS: Placeholder[] = [
  { key: 'filament_diameter', name: 'filament_diameter', description: 'Filament diameter', type: 'filament_vector', category: 'Filament Settings' },
  { key: 'filament_density', name: 'filament_density', description: 'Filament density', type: 'filament_vector', category: 'Filament Settings' },
  { key: 'filament_cost', name: 'filament_cost', description: 'Filament cost per gram', type: 'filament_vector', category: 'Filament Settings' },
  { key: 'filament_type', name: 'filament_type', description: 'Filament material type', type: 'filament_vector', category: 'Filament Settings' },
  { key: 'filament_vendor', name: 'filament_vendor', description: 'Filament vendor', type: 'filament_vector', category: 'Filament Settings' },
  { key: 'nozzle_temperature', name: 'nozzle_temperature', description: 'Nozzle temperature', type: 'filament_vector', category: 'Filament Settings' },
  { key: 'bed_temperature', name: 'bed_temperature', description: 'Bed temperature', type: 'filament_vector', category: 'Filament Settings' },
];

export const EditGCodeModal: React.FC<EditGCodeModalProps> = ({
  isOpen,
  onClose,
  onInsert,
  title,
  gcodeType,
}) => {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set(['Temperatures', 'Dimensions']));

  // Filter placeholders based on G-code type
  const availablePlaceholders = useMemo(() => {
    if (!gcodeType) return [...PLACEHOLDERS, ...FILAMENT_PLACEHOLDERS];
    
    // For filament_start_gcode: only filament_extruder_id
    if (gcodeType === 'filament_start_gcode') {
      return [
        { key: 'filament_extruder_id', name: 'filament_extruder_id', description: 'The current extruder ID (same as current_extruder)', type: 'scalar' as const, category: 'Filament G-code' },
        ...PLACEHOLDERS.filter(p => !['layer_num', 'layer_z', 'max_layer_z'].includes(p.key)),
        ...FILAMENT_PLACEHOLDERS,
      ];
    }
    
    // For filament_end_gcode: layer_num, layer_z, max_layer_z, filament_extruder_id
    if (gcodeType === 'filament_end_gcode') {
      return [
        { key: 'layer_num', name: 'layer_num', description: 'Index of the current layer (one-based, first layer is 1)', type: 'scalar' as const, category: 'Filament G-code' },
        { key: 'layer_z', name: 'layer_z', description: 'Height of the current layer above the print bed', type: 'scalar' as const, category: 'Filament G-code' },
        { key: 'max_layer_z', name: 'max_layer_z', description: 'Height of the last layer above the print bed', type: 'scalar' as const, category: 'Filament G-code' },
        { key: 'filament_extruder_id', name: 'filament_extruder_id', description: 'The current extruder ID (same as current_extruder)', type: 'scalar' as const, category: 'Filament G-code' },
        ...PLACEHOLDERS.filter(p => !['layer_num', 'layer_z'].includes(p.key)),
        ...FILAMENT_PLACEHOLDERS,
      ];
    }
    
    return [...PLACEHOLDERS, ...FILAMENT_PLACEHOLDERS];
  }, [gcodeType]);

  // Группируем плейсхолдеры по категориям и подкатегориям
  const categories = useMemo(() => {
    const cats: Record<string, Record<string, Placeholder[]>> = {};
    availablePlaceholders.forEach(p => {
      const category = p.category;
      const subcategory = p.subcategory || '_default';
      
      if (!cats[category]) {
        cats[category] = {};
      }
      if (!cats[category][subcategory]) {
        cats[category][subcategory] = [];
      }
      cats[category][subcategory].push(p);
    });
    return cats;
  }, [availablePlaceholders]);

  // Фильтруем плейсхолдеры по поисковому запросу
  const filteredCategories = useMemo(() => {
    if (!searchQuery.trim()) {
      return categories;
    }

    const query = searchQuery.toLowerCase();
    const filtered: Record<string, Record<string, Placeholder[]>> = {};
    
    Object.keys(categories).forEach(cat => {
      const matchingSubcats: Record<string, Placeholder[]> = {};
      Object.keys(categories[cat]).forEach(subcat => {
        const matching = categories[cat][subcat].filter(p => 
          p.key.toLowerCase().includes(query) || 
          p.name.toLowerCase().includes(query) ||
          (p.description && p.description.toLowerCase().includes(query)) ||
          (p.subcategory && p.subcategory.toLowerCase().includes(query))
        );
        if (matching.length > 0) {
          matchingSubcats[subcat] = matching;
        }
      });
      if (Object.keys(matchingSubcats).length > 0) {
        filtered[cat] = matchingSubcats;
      }
    });
    
    return filtered;
  }, [categories, searchQuery]);

  const formatPlaceholder = (placeholder: Placeholder): string => {
    if (placeholder.type === 'vector') {
      return `{${placeholder.key}[]}`;
    } else if (placeholder.type === 'filament_vector') {
      return `{${placeholder.key}[current_extruder]}`;
    }
    return `{${placeholder.key}}`;
  };

  const handleInsertPlaceholder = (placeholder: Placeholder) => {
    const formatted = formatPlaceholder(placeholder);
    onInsert(formatted);
  };

  const toggleCategory = (category: string) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  if (!isOpen) return null;

  return (
    <div className="relative flex-shrink-0 w-[380px] h-[258px] bg-gray-900 rounded-lg border border-white/20 shadow-xl flex flex-col" onClick={(e) => e.stopPropagation()} onMouseDown={(e) => e.stopPropagation()}>
      {/* Search */}
      <div className="p-3 border-b border-white/10">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('editGCode.searchPlaceholder')}
            className="w-full pl-8 pr-3 py-1.5 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Placeholders List */}
      <div className="flex-1 overflow-y-auto p-2">
        {Object.keys(filteredCategories).length === 0 ? (
          <div className="text-center text-gray-500 text-xs py-6">
            No placeholders found
          </div>
        ) : (
          Object.keys(filteredCategories).map(category => (
            <div key={category} className="mb-2">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleCategory(category);
                }}
                onMouseDown={(e) => e.stopPropagation()}
                className="w-full flex items-center justify-between px-2 py-1 text-xs font-medium text-gray-300 hover:text-white hover:bg-white/5 rounded transition-colors"
              >
                <span>{category}</span>
                {expandedCategories.has(category) ? (
                  <ChevronDown className="w-3 h-3" />
                ) : (
                  <ChevronRight className="w-3 h-3" />
                )}
              </button>
              
              {expandedCategories.has(category) && (
                <div className="ml-2 mt-0.5 space-y-1">
                  {Object.keys(filteredCategories[category]).map(subcategory => {
                    const placeholders = filteredCategories[category][subcategory];
                    if (placeholders.length === 0) return null;
                    
                    return (
                      <div key={subcategory}>
                        {subcategory !== '_default' && (
                          <div className="text-[10px] text-gray-500 px-2 py-0.5 mb-0.5">{subcategory}</div>
                        )}
                        <div className="space-y-0.5">
                          {placeholders.map(placeholder => (
                            <button
                              key={placeholder.key}
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                e.preventDefault();
                                handleInsertPlaceholder(placeholder);
                                // Не закрываем модальное окно плейсхолдеров - оно всегда открыто
                                // onClose();
                              }}
                              onMouseDown={(e) => {
                                e.stopPropagation();
                                e.preventDefault();
                              }}
                              className="w-full text-left px-2 py-1 text-[11px] rounded transition-colors text-gray-400 hover:text-white hover:bg-purple-500/20 border border-transparent hover:border-purple-500/30"
                              title={placeholder.description}
                            >
                              <div className="font-mono text-[10px] text-purple-300">{formatPlaceholder(placeholder)}</div>
                              {placeholder.description && (
                                <div className="text-gray-500 text-[10px] mt-0.5 truncate">{placeholder.description}</div>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};

