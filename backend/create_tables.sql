-- SQL скрипт для создания таблиц FilamentHub
-- Выполните этот скрипт в PostgreSQL после создания базы filamenthub

CREATE TABLE IF NOT EXISTS brands (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    website VARCHAR(255),
    logo_url VARCHAR(500),
    verified BOOLEAN DEFAULT FALSE,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS filaments (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    material_type VARCHAR(50) NOT NULL,
    color_name VARCHAR(100),
    color_hex VARCHAR(7),
    diameter FLOAT DEFAULT 1.75,
    density FLOAT,
    price_per_kg FLOAT,
    spool_weight FLOAT,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS presets (
    id SERIAL PRIMARY KEY,
    filament_id INTEGER NOT NULL REFERENCES filaments(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_official BOOLEAN DEFAULT FALSE,
    extruder_temp FLOAT NOT NULL,
    bed_temp FLOAT NOT NULL,
    print_speed FLOAT NOT NULL,
    travel_speed FLOAT,
    layer_height FLOAT,
    first_layer_height FLOAT,
    flow_rate FLOAT,
    fan_speed INTEGER,
    retraction_length FLOAT,
    retraction_speed FLOAT,
    rating FLOAT,
    usage_count INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Индексы для производительности
CREATE INDEX IF NOT EXISTS idx_brands_name ON brands(name);
CREATE INDEX IF NOT EXISTS idx_brands_slug ON brands(slug);
CREATE INDEX IF NOT EXISTS idx_brands_verified ON brands(verified);
CREATE INDEX IF NOT EXISTS idx_brands_active ON brands(active);

CREATE INDEX IF NOT EXISTS idx_filaments_brand_id ON filaments(brand_id);
CREATE INDEX IF NOT EXISTS idx_filaments_material_type ON filaments(material_type);
CREATE INDEX IF NOT EXISTS idx_filaments_active ON filaments(active);

CREATE INDEX IF NOT EXISTS idx_presets_filament_id ON presets(filament_id);
CREATE INDEX IF NOT EXISTS idx_presets_is_official ON presets(is_official);
CREATE INDEX IF NOT EXISTS idx_presets_active ON presets(active);

