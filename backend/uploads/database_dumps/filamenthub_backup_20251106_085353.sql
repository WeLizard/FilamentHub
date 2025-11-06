--
-- PostgreSQL database dump
--

\restrict DISllJZP2tIdn1z2NvVt7zuyuLLr3tsWurLxchfRHPimgrbgKqovpMdSodThc8Z

-- Dumped from database version 15.14
-- Dumped by pg_dump version 17.6 (Debian 17.6-0+deb13u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: brandrequeststatus; Type: TYPE; Schema: public; Owner: filamenthub
--

CREATE TYPE public.brandrequeststatus AS ENUM (
    'pending',
    'approved',
    'rejected'
);


ALTER TYPE public.brandrequeststatus OWNER TO filamenthub;

--
-- Name: brandrequesttype; Type: TYPE; Schema: public; Owner: filamenthub
--

CREATE TYPE public.brandrequesttype AS ENUM (
    'join',
    'create'
);


ALTER TYPE public.brandrequesttype OWNER TO filamenthub;

--
-- Name: materialmappingpriority; Type: TYPE; Schema: public; Owner: filamenthub
--

CREATE TYPE public.materialmappingpriority AS ENUM (
    'automatic',
    'manual',
    'brand'
);


ALTER TYPE public.materialmappingpriority OWNER TO filamenthub;

--
-- Name: presetmoderationstatus; Type: TYPE; Schema: public; Owner: filamenthub
--

CREATE TYPE public.presetmoderationstatus AS ENUM (
    'pending',
    'approved',
    'rejected'
);


ALTER TYPE public.presetmoderationstatus OWNER TO filamenthub;

--
-- Name: printerrequeststatus; Type: TYPE; Schema: public; Owner: filamenthub
--

CREATE TYPE public.printerrequeststatus AS ENUM (
    'pending',
    'approved',
    'rejected'
);


ALTER TYPE public.printerrequeststatus OWNER TO filamenthub;

--
-- Name: userrole; Type: TYPE; Schema: public; Owner: filamenthub
--

CREATE TYPE public.userrole AS ENUM (
    'user',
    'brand',
    'admin'
);


ALTER TYPE public.userrole OWNER TO filamenthub;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO filamenthub;

--
-- Name: brand_requests; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.brand_requests (
    id integer NOT NULL,
    user_id integer NOT NULL,
    request_type public.brandrequesttype NOT NULL,
    brand_id integer,
    new_brand_name character varying(100),
    new_brand_slug character varying(100),
    new_brand_description text,
    new_brand_website character varying(255),
    message text,
    proof_text text,
    company_email character varying(255),
    company_website character varying(500),
    social_media_urls text,
    proof_files text,
    status public.brandrequeststatus DEFAULT 'pending'::public.brandrequeststatus NOT NULL,
    processed_by_id integer,
    processed_at timestamp without time zone,
    rejection_reason text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.brand_requests OWNER TO filamenthub;

--
-- Name: brand_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.brand_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.brand_requests_id_seq OWNER TO filamenthub;

--
-- Name: brand_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.brand_requests_id_seq OWNED BY public.brand_requests.id;


--
-- Name: brands; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.brands (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    slug character varying(100) NOT NULL,
    description text,
    website character varying(255),
    logo_url character varying(500),
    verified boolean NOT NULL,
    active boolean NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.brands OWNER TO filamenthub;

--
-- Name: brands_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.brands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.brands_id_seq OWNER TO filamenthub;

--
-- Name: brands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.brands_id_seq OWNED BY public.brands.id;


--
-- Name: filament_reviews; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.filament_reviews (
    id integer NOT NULL,
    filament_id integer NOT NULL,
    user_id integer NOT NULL,
    success boolean NOT NULL,
    rating double precision NOT NULL,
    comment text,
    printer_model text,
    active boolean NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    preset_id integer
);


ALTER TABLE public.filament_reviews OWNER TO filamenthub;

--
-- Name: filament_reviews_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.filament_reviews_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.filament_reviews_id_seq OWNER TO filamenthub;

--
-- Name: filament_reviews_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.filament_reviews_id_seq OWNED BY public.filament_reviews.id;


--
-- Name: filaments; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.filaments (
    id integer NOT NULL,
    brand_id integer NOT NULL,
    name character varying(200) NOT NULL,
    material_type character varying(50) NOT NULL,
    color_name character varying(100),
    color_hex character varying(7),
    diameter double precision NOT NULL,
    density double precision,
    price_per_kg double precision,
    spool_weight double precision,
    description text,
    active boolean NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    views_count integer DEFAULT 0 NOT NULL,
    scans_count integer DEFAULT 0 NOT NULL,
    visual_settings jsonb,
    qr_code character varying(50)
);


ALTER TABLE public.filaments OWNER TO filamenthub;

--
-- Name: filaments_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.filaments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.filaments_id_seq OWNER TO filamenthub;

--
-- Name: filaments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.filaments_id_seq OWNED BY public.filaments.id;


--
-- Name: material_mappings; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.material_mappings (
    id integer NOT NULL,
    material_type character varying(100) NOT NULL,
    orcaslicer_preset character varying(200) NOT NULL,
    priority public.materialmappingpriority NOT NULL,
    brand_id integer,
    description text,
    active boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.material_mappings OWNER TO filamenthub;

--
-- Name: material_mappings_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.material_mappings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.material_mappings_id_seq OWNER TO filamenthub;

--
-- Name: material_mappings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.material_mappings_id_seq OWNED BY public.material_mappings.id;


--
-- Name: preset_printers; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.preset_printers (
    id integer NOT NULL,
    preset_id integer NOT NULL,
    printer_id integer NOT NULL,
    is_primary boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.preset_printers OWNER TO filamenthub;

--
-- Name: preset_printers_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.preset_printers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.preset_printers_id_seq OWNER TO filamenthub;

--
-- Name: preset_printers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.preset_printers_id_seq OWNED BY public.preset_printers.id;


--
-- Name: presets; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.presets (
    id integer NOT NULL,
    filament_id integer NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    is_official boolean NOT NULL,
    extruder_temp double precision NOT NULL,
    bed_temp double precision NOT NULL,
    print_speed double precision NOT NULL,
    travel_speed double precision,
    layer_height double precision,
    first_layer_height double precision,
    flow_rate double precision,
    fan_speed integer,
    retraction_length double precision,
    retraction_speed double precision,
    rating double precision,
    usage_count integer NOT NULL,
    active boolean NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    moderation_status public.presetmoderationstatus DEFAULT 'pending'::public.presetmoderationstatus NOT NULL,
    moderation_reason text,
    moderated_by integer,
    moderated_at timestamp with time zone,
    user_id integer,
    success_rate double precision,
    orcaslicer_settings jsonb
);


ALTER TABLE public.presets OWNER TO filamenthub;

--
-- Name: presets_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.presets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.presets_id_seq OWNER TO filamenthub;

--
-- Name: presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.presets_id_seq OWNED BY public.presets.id;


--
-- Name: printer_requests; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.printer_requests (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(200) NOT NULL,
    manufacturer character varying(100) NOT NULL,
    model character varying(100) NOT NULL,
    slug character varying(200) NOT NULL,
    description text,
    build_volume_x double precision,
    build_volume_y double precision,
    build_volume_z double precision,
    nozzle_diameter double precision,
    max_extruder_temp integer,
    max_bed_temp integer,
    image_url character varying(500),
    message text,
    proof_files text,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    processed_by_id integer,
    processed_at timestamp without time zone,
    rejection_reason text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.printer_requests OWNER TO filamenthub;

--
-- Name: printer_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.printer_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.printer_requests_id_seq OWNER TO filamenthub;

--
-- Name: printer_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.printer_requests_id_seq OWNED BY public.printer_requests.id;


--
-- Name: printers; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.printers (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    manufacturer character varying(100) NOT NULL,
    model character varying(100) NOT NULL,
    slug character varying(200) NOT NULL,
    build_volume_x double precision,
    build_volume_y double precision,
    build_volume_z double precision,
    nozzle_diameter double precision,
    max_extruder_temp integer,
    max_bed_temp integer,
    description text,
    image_url character varying(500),
    active boolean NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.printers OWNER TO filamenthub;

--
-- Name: printers_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.printers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.printers_id_seq OWNER TO filamenthub;

--
-- Name: printers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.printers_id_seq OWNED BY public.printers.id;


--
-- Name: user_saved_presets; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.user_saved_presets (
    id integer NOT NULL,
    user_id integer NOT NULL,
    preset_id integer NOT NULL,
    saved_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.user_saved_presets OWNER TO filamenthub;

--
-- Name: user_saved_presets_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.user_saved_presets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_saved_presets_id_seq OWNER TO filamenthub;

--
-- Name: user_saved_presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.user_saved_presets_id_seq OWNED BY public.user_saved_presets.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.users (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    username character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role public.userrole DEFAULT 'user'::public.userrole NOT NULL,
    api_key character varying(64),
    full_name character varying(255),
    bio text,
    active boolean NOT NULL,
    email_verified boolean NOT NULL,
    brand_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_login timestamp with time zone,
    printer_id integer
);


ALTER TABLE public.users OWNER TO filamenthub;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO filamenthub;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: brand_requests id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.brand_requests ALTER COLUMN id SET DEFAULT nextval('public.brand_requests_id_seq'::regclass);


--
-- Name: brands id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.brands ALTER COLUMN id SET DEFAULT nextval('public.brands_id_seq'::regclass);


--
-- Name: filament_reviews id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filament_reviews ALTER COLUMN id SET DEFAULT nextval('public.filament_reviews_id_seq'::regclass);


--
-- Name: filaments id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filaments ALTER COLUMN id SET DEFAULT nextval('public.filaments_id_seq'::regclass);


--
-- Name: material_mappings id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.material_mappings ALTER COLUMN id SET DEFAULT nextval('public.material_mappings_id_seq'::regclass);


--
-- Name: preset_printers id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.preset_printers ALTER COLUMN id SET DEFAULT nextval('public.preset_printers_id_seq'::regclass);


--
-- Name: presets id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.presets ALTER COLUMN id SET DEFAULT nextval('public.presets_id_seq'::regclass);


--
-- Name: printer_requests id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.printer_requests ALTER COLUMN id SET DEFAULT nextval('public.printer_requests_id_seq'::regclass);


--
-- Name: printers id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.printers ALTER COLUMN id SET DEFAULT nextval('public.printers_id_seq'::regclass);


--
-- Name: user_saved_presets id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.user_saved_presets ALTER COLUMN id SET DEFAULT nextval('public.user_saved_presets_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.alembic_version (version_num) FROM stdin;
a2b3c4d5e6f7
\.


--
-- Data for Name: brand_requests; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.brand_requests (id, user_id, request_type, brand_id, new_brand_name, new_brand_slug, new_brand_description, new_brand_website, message, proof_text, company_email, company_website, social_media_urls, proof_files, status, processed_by_id, processed_at, rejection_reason, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: brands; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.brands (id, name, slug, description, website, logo_url, verified, active, created_at, updated_at) FROM stdin;
2	Sunlu	sunlu	Популярный китайский бренд	https://www.sunlu.com	\N	t	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547
3	eSUN	esun	Профессиональные материалы для 3D-печати	https://www.esun3d.com	\N	t	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547
4	Polymaker	polymaker	Премиум материалы из Китая	https://polymaker.com	\N	t	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547
5	H-T-P	h-t-p	Российский производитель качественных филаментов для 3D-печати	https://h-t-p.ru/	\N	t	t	2025-11-01 09:36:14.378411	2025-11-01 09:36:14.378411
6	BrandNew	brandnew	\N	\N	\N	f	t	2025-11-01 10:01:54.389319	2025-11-01 10:01:54.389319
1	Bestfilament	bestfilament	Российский производитель качественного пластика	https://bestfilament.ru	\N	t	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547
\.


--
-- Data for Name: filament_reviews; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.filament_reviews (id, filament_id, user_id, success, rating, comment, printer_model, active, created_at, updated_at, preset_id) FROM stdin;
\.


--
-- Data for Name: filaments; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.filaments (id, brand_id, name, material_type, color_name, color_hex, diameter, density, price_per_kg, spool_weight, description, active, created_at, updated_at, views_count, scans_count, visual_settings, qr_code) FROM stdin;
1	1	PLA Red	PLA	Red	#FF0000	1.75	1.24	800	1000	Красный PLA от Bestfilament	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547	0	0	\N	\N
2	1	PLA Blue	PLA	Blue	#0000FF	1.75	1.24	800	1000	Синий PLA от Bestfilament	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547	0	0	\N	\N
3	2	PETG Black	PETG	Black	#000000	1.75	1.27	950	1000	Черный PETG от Sunlu	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547	0	0	\N	\N
4	2	PLA+ White	PLA	White	#FFFFFF	1.75	1.24	850	1000	Белый PLA+ от Sunlu	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547	0	0	\N	\N
5	3	TPU 95A	TPU	Transparent	#FFFFFF	1.75	1.2	1800	500	Прозрачный TPU от eSUN	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547	0	0	\N	\N
6	4	PolyTerra PLA	PLA	Natural	#F5E6D3	1.75	1.24	1200	1000	Экологичный PLA от Polymaker	t	2025-10-31 08:06:54.343547	2025-10-31 08:06:54.343547	0	0	\N	\N
7	1	Test PLA Without Official	PLA	Red	#ff0000	1.75	1.24	800	1000	Test filament without official preset	t	2025-11-01 06:39:37.260548	2025-11-01 06:39:37.260548	0	0	\N	\N
8	5	PETG-1 - графит	PETG	Graphite	#2F2F2F	1.75	1.27	1200	1000	Качественный PETG-1 графит цвета. Масса нетто – 1 кг (+/-50 г). Диаметр прутка - 1,75 мм (+/- 0,05 мм).	t	2025-11-01 09:36:14.392783	2025-11-01 09:36:14.392783	0	0	\N	\N
9	5	PETG-1 - бежевый золотистый	PETG	Beige Golden	#DAA520	1.75	1.27	1200	1000	PETG-1 бежевый золотистый. Масса нетто – 1 кг (+/-50 г). Диаметр прутка - 1,75 мм (+/- 0,05 мм).	t	2025-11-01 09:36:14.405672	2025-11-01 09:36:14.405672	0	0	\N	\N
10	5	PETG-1 - жёлтый-2	PETG	Yellow	#FFD700	1.75	1.27	1200	1000	PETG-1 ярко-жёлтый. Масса нетто – 1 кг (+/-50 г). Диаметр прутка - 1,75 мм (+/- 0,05 мм).	t	2025-11-01 09:36:14.412827	2025-11-01 09:36:14.412827	0	0	\N	\N
11	5	ABS-6 - чёрный	ABS	Black	#000000	1.75	1.04	900	1000	ABS-6 чёрный. Масса нетто – 1 кг (+/-50 г). Диаметр филамента - 1,75 мм (+/- 0,05 мм).	t	2025-11-01 09:36:14.420095	2025-11-01 09:36:14.420095	0	0	\N	\N
12	5	ABS-6 - лимонный	ABS	Lemon Yellow	#FFF700	1.75	1.04	900	1000	ABS-6 лимонный. Масса нетто – 1 кг (+/-50 г). Диаметр филамента - 1,75 мм (+/- 0,05 мм).	t	2025-11-01 09:36:14.427433	2025-11-01 09:36:14.427433	0	0	\N	\N
13	5	ABS-6 - коричневый-2	ABS	Brown	#8B4513	1.75	1.04	900	1000	ABS-6 коричневый. Масса нетто – 1 кг (+/-50 г). Диаметр филамента - 1,75 мм (+/- 0,05 мм).	t	2025-11-01 09:36:14.434906	2025-11-01 09:36:14.434906	0	0	\N	\N
14	5	HIPS - натуральный	HIPS	Natural	#FFF8DC	1.75	1.05	750	850	HIPS натуральный. Масса нетто – 0,85 кг (+/-50 г). Диаметр филамента - 1,75 мм (+/- 0,05 мм).	t	2025-11-01 09:36:14.44257	2025-11-01 09:36:14.44257	0	0	\N	\N
15	5	PLA - чёрный	PLA	Black	#000000	1.75	1.24	1250	1000	PLA чёрный. Масса нетто – 1 кг (+/-50 г). Диаметр прутка 1,75 мм.	t	2025-11-01 09:36:14.448886	2025-11-01 09:36:14.448886	0	0	\N	\N
16	6	Super PLA Blue	PLA	Blue	#FF0000	1.75	1.24	\N	\N	\N	t	2025-11-01 10:01:54.648095	2025-11-01 10:01:54.648095	0	0	\N	\N
\.


--
-- Data for Name: material_mappings; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.material_mappings (id, material_type, orcaslicer_preset, priority, brand_id, description, active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: preset_printers; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.preset_printers (id, preset_id, printer_id, is_primary, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: presets; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.presets (id, filament_id, name, description, is_official, extruder_temp, bed_temp, print_speed, travel_speed, layer_height, first_layer_height, flow_rate, fan_speed, retraction_length, retraction_speed, rating, usage_count, active, created_at, updated_at, moderation_status, moderation_reason, moderated_by, moderated_at, user_id, success_rate, orcaslicer_settings) FROM stdin;
1	1	Официальный пресет Bestfilament	Рекомендуемые настройки от производителя	t	200	60	50	150	0.2	\N	100	100	5	45	4.8	245	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
2	2	Официальный пресет Bestfilament	Рекомендуемые настройки от производителя	t	200	60	50	150	0.2	\N	100	100	5	45	4.8	189	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
3	3	Официальный пресет Sunlu	Рекомендуемые настройки от производителя	t	240	80	40	150	0.2	\N	98	50	6	40	4.9	312	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
4	4	Официальный пресет Sunlu	Рекомендуемые настройки от производителя	t	210	60	55	150	0.2	\N	100	100	5	45	4.8	198	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
5	5	Официальный пресет eSUN	Рекомендуемые настройки от производителя	t	230	50	25	100	0.2	\N	95	0	3	30	4.7	156	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
6	6	Официальный пресет Polymaker	Рекомендуемые настройки от производителя	t	205	60	50	150	0.2	\N	100	100	5	45	4.8	234	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
7	1	3D_Guru	Проверенная настройка для Ender 3 Pro	f	195	60	45	150	0.2	\N	100	100	5	45	4.8	124	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
8	1	PrintMaster	Оптимизированная настройка для высокой скорости	f	205	55	55	150	0.2	\N	100	100	5	45	4.5	87	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
9	3	PETG_Pro	Оптимальные настройки для прочности	f	235	85	35	150	0.2	\N	98	50	6	40	4.9	156	t	2025-11-01 05:32:00.98392	2025-11-01 05:32:00.98392	approved	\N	\N	\N	\N	\N	\N
11	7	Community Test Preset 1	Test community preset	f	210	60	50	150	0.2	\N	100	100	5	45	4.9	100	t	2025-11-01 06:39:56.574609	2025-11-01 06:39:56.574609	approved	\N	\N	\N	\N	\N	\N
12	7	Community Test Preset 2	Another test preset	f	215	65	55	150	0.2	\N	100	100	5	45	4.7	50	t	2025-11-01 06:39:56.574609	2025-11-01 06:39:56.574609	approved	\N	\N	\N	\N	\N	\N
13	7	Официальный пресет TestBrand	\N	t	200	60	50	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-01 06:42:08.022188	2025-11-01 06:42:08.022188	approved	\N	\N	\N	\N	\N	\N
15	8	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	240	80	50	150	0.2	\N	98	50	5	40	4.8	342	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
16	8	PETG_Pro_Speed	Высокая скорость печати для PETG	f	245	85	70	200	0.25	\N	100	60	5.5	45	4.6	156	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
17	8	Smooth_Finish	Гладкая поверхность для детальных моделей	f	238	75	35	120	0.15	\N	96	30	4.5	35	4.9	234	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
18	8	Strong_Layers	Максимальная прочность слоёв	f	250	90	40	150	0.25	\N	102	20	6	50	4.7	187	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
19	8	Ender3_Profile	Оптимизировано для Ender 3	f	242	82	45	150	0.2	\N	97	40	5	42	4.8	298	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
20	8	Fast_Prototype	Быстрое прототипирование	f	235	70	80	250	0.3	\N	110	80	7	60	4.3	124	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
21	11	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	250	90	50	150	0.2	\N	100	0	5	45	4.7	278	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
22	11	ABS_Strength	Максимальная прочность ABS	f	260	95	40	120	0.25	\N	105	0	4	40	4.8	198	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
23	11	No_Warp	Минимальная деформация	f	255	100	35	100	0.2	\N	98	0	5.5	50	4.9	345	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
24	11	Quick_Print	Быстрая печать ABS	f	245	85	70	200	0.3	\N	110	20	6	60	4.4	156	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
25	11	Desktop_Fan	Для печати в комнате	f	248	88	45	150	0.2	\N	100	30	5	45	4.6	267	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
26	11	Enclosure_Optimal	Для камеры с нагревом	f	265	105	55	150	0.25	\N	102	0	4.5	40	4.9	312	t	2025-11-01 09:36:14.457204	2025-11-01 09:36:14.457204	approved	\N	\N	\N	\N	\N	\N
27	9	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	240	80	50	150	0.2	\N	98	50	5	40	4.8	245	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
28	9	Golden_Finish	Особые настройки для золотистого цвета	f	242	78	40	140	0.18	\N	97	40	5.2	38	4.7	134	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
29	9	Flow_Optimized	Оптимизированный поток для деталей	f	238	82	45	150	0.2	\N	96	55	5.5	42	4.6	167	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
30	10	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	240	80	50	150	0.2	\N	98	50	5	40	4.8	198	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
31	10	Bright_Yellow	Яркий жёлтый цвет	f	243	79	42	145	0.2	\N	99	45	5	41	4.8	156	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
32	10	Visibility_Max	Максимальная видимость детали	f	241	81	48	155	0.2	\N	98	52	5	40	4.9	213	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
33	12	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	250	90	50	150	0.2	\N	100	0	5	45	4.7	167	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
34	12	Lemon_Fresh	Для яркого лимонного цвета	f	252	92	46	148	0.2	\N	101	0	5.2	46	4.7	123	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
35	12	Bright_ABS	Яркий цвет для декора	f	248	88	52	155	0.25	\N	102	15	5	45	4.6	145	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
36	13	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	250	90	50	150	0.2	\N	100	0	5	45	4.7	178	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
37	13	Wood_Look	Древесный вид	f	253	91	44	145	0.2	\N	99	0	5.5	44	4.8	198	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
38	13	Natural_Tone	Естественный коричневый	f	247	89	48	152	0.2	\N	100	10	5	45	4.7	167	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
39	15	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	210	60	50	150	0.2	\N	100	100	5	45	4.8	234	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
40	15	Deep_Black	Глубокий чёрный цвет	f	212	62	46	148	0.18	\N	98	100	5.5	47	4.9	267	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
41	15	Glossy_Finish	Глянцевая поверхность	f	208	58	48	155	0.2	\N	102	90	4.5	43	4.7	189	t	2025-11-01 09:38:15.155725	2025-11-01 09:38:15.155725	approved	\N	\N	\N	\N	\N	\N
42	14	Официальный пресет H-T-P	Рекомендуемые настройки от производителя	t	245	100	60	150	0.2	\N	100	100	5	45	4.7	198	t	2025-11-01 09:39:11.354398	2025-11-01 09:39:11.354398	approved	\N	\N	\N	\N	\N	\N
43	14	Support_Material	Оптимизировано для поддержек	f	248	105	55	145	0.25	\N	105	100	5.5	47	4.8	267	t	2025-11-01 09:39:11.354398	2025-11-01 09:39:11.354398	approved	\N	\N	\N	\N	\N	\N
44	14	Dissolvable_Pro	Для растворяемых поддержек	f	242	98	58	155	0.2	\N	98	90	5	46	4.9	312	t	2025-11-01 09:39:11.354398	2025-11-01 09:39:11.354398	approved	\N	\N	\N	\N	\N	\N
14	1	Test PLA Red Preset	213м	f	205	60	50	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-01 08:09:20.572838	2025-11-01 09:19:40.603498	approved	\N	\N	\N	5	\N	\N
45	16	Test Preset BrandNew	\N	f	200	60	50	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-01 10:01:54.721655	2025-11-01 10:01:54.721655	approved	\N	\N	\N	5	\N	\N
\.


--
-- Data for Name: printer_requests; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.printer_requests (id, user_id, name, manufacturer, model, slug, description, build_volume_x, build_volume_y, build_volume_z, nozzle_diameter, max_extruder_temp, max_bed_temp, image_url, message, proof_files, status, processed_by_id, processed_at, rejection_reason, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: printers; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.printers (id, name, manufacturer, model, slug, build_volume_x, build_volume_y, build_volume_z, nozzle_diameter, max_extruder_temp, max_bed_temp, description, image_url, active, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: user_saved_presets; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.user_saved_presets (id, user_id, preset_id, saved_at) FROM stdin;
4	5	1	2025-11-01 09:29:41.218005+00
5	5	7	2025-11-01 09:31:42.231767+00
6	5	12	2025-11-01 09:35:01.210654+00
7	5	13	2025-11-01 09:35:03.55609+00
8	5	23	2025-11-01 09:40:16.378546+00
9	5	37	2025-11-01 09:40:20.931259+00
10	5	36	2025-11-01 09:40:59.654254+00
11	5	33	2025-11-05 12:39:48.199207+00
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.users (id, email, username, password_hash, role, api_key, full_name, bio, active, email_verified, brand_id, created_at, updated_at, last_login, printer_id) FROM stdin;
1	test@example.com	testuser	$2b$12$c3iAdaLgxtMkTJWlEHfBTeO1zJrGc8TJfnnMiPIKlO1IUmYcS9u22	user	\N	\N	\N	t	f	\N	2025-11-01 05:41:46.360978+00	2025-11-01 05:41:46.360978+00	\N	\N
2	test3@example.com	testuser3	$2b$12$PPBkD5fIYRi5TfYDIHe.rufCFqzO4PQbV8Qu01pvRdu0wAo8XFIaO	user	\N	\N	\N	t	f	\N	2025-11-01 05:43:31.815535+00	2025-11-01 05:43:31.815535+00	\N	\N
3	test8200@example.com	testuser8200	$2b$12$mPa5GMAp4qhLYYBLrboYOuM8Mib9SzShM3rqfh6OOrXKwRPByhjzy	user	\N	\N	\N	t	f	\N	2025-11-01 05:46:10.345774+00	2025-11-01 05:46:10.611001+00	2025-11-01 05:46:10.804065+00	\N
4	brand@test.com	TestBrand	$2b$12$JePhSuzNSN3/BmZGn.6fyeY2SMYMAvbHA1C9kyY3cvgp/tRzsQJAa	brand	\N	\N	\N	t	f	\N	2025-11-01 06:41:22.734998+00	2025-11-01 06:41:23.27493+00	2025-11-01 06:41:23.473052+00	\N
6	newuser123@test.com	newuser123	$2b$12$H4vSgt1IxJ7qJ4zEYJLtyuBaq0gK9NvtEvbAgzeIi/WZNL2gnMlkq	user	\N	\N	\N	t	f	\N	2025-11-05 11:05:48.652208+00	2025-11-05 11:05:48.652208+00	\N	\N
5	123@example.ru	123	$2b$12$3i/MWINIDVlbipUMkvHN9OeQsAF0g6s9J.cr6OFCZxLBUS1kyzhaq	user	\N	\N	\N	t	f	\N	2025-11-01 06:45:44.455256+00	2025-11-05 13:46:58.128086+00	2025-11-05 13:46:58.342017+00	\N
7	admin@filamenthub.ru	admin	$2b$12$tw8FRWiQyFFfReXjrLJifet7dpfRckhem0A07yCzcRxwdSQVXkmBi	admin	\N	\N	\N	t	t	\N	2025-11-06 06:51:39.448493+00	2025-11-06 07:13:30.447372+00	2025-11-06 07:13:30.635529+00	\N
\.


--
-- Name: brand_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.brand_requests_id_seq', 1, false);


--
-- Name: brands_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.brands_id_seq', 6, true);


--
-- Name: filament_reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.filament_reviews_id_seq', 1, false);


--
-- Name: filaments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.filaments_id_seq', 16, true);


--
-- Name: material_mappings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.material_mappings_id_seq', 1, false);


--
-- Name: preset_printers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.preset_printers_id_seq', 1, false);


--
-- Name: presets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.presets_id_seq', 45, true);


--
-- Name: printer_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.printer_requests_id_seq', 1, false);


--
-- Name: printers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.printers_id_seq', 1, false);


--
-- Name: user_saved_presets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.user_saved_presets_id_seq', 11, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.users_id_seq', 7, true);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: brand_requests brand_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.brand_requests
    ADD CONSTRAINT brand_requests_pkey PRIMARY KEY (id);


--
-- Name: brands brands_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.brands
    ADD CONSTRAINT brands_pkey PRIMARY KEY (id);


--
-- Name: filament_reviews filament_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filament_reviews
    ADD CONSTRAINT filament_reviews_pkey PRIMARY KEY (id);


--
-- Name: filaments filaments_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filaments
    ADD CONSTRAINT filaments_pkey PRIMARY KEY (id);


--
-- Name: material_mappings material_mappings_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.material_mappings
    ADD CONSTRAINT material_mappings_pkey PRIMARY KEY (id);


--
-- Name: preset_printers preset_printers_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.preset_printers
    ADD CONSTRAINT preset_printers_pkey PRIMARY KEY (id);


--
-- Name: presets presets_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.presets
    ADD CONSTRAINT presets_pkey PRIMARY KEY (id);


--
-- Name: printer_requests printer_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.printer_requests
    ADD CONSTRAINT printer_requests_pkey PRIMARY KEY (id);


--
-- Name: printers printers_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.printers
    ADD CONSTRAINT printers_pkey PRIMARY KEY (id);


--
-- Name: user_saved_presets user_saved_presets_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.user_saved_presets
    ADD CONSTRAINT user_saved_presets_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_brand_requests_brand_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brand_requests_brand_id ON public.brand_requests USING btree (brand_id);


--
-- Name: ix_brand_requests_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brand_requests_id ON public.brand_requests USING btree (id);


--
-- Name: ix_brand_requests_request_type; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brand_requests_request_type ON public.brand_requests USING btree (request_type);


--
-- Name: ix_brand_requests_status; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brand_requests_status ON public.brand_requests USING btree (status);


--
-- Name: ix_brand_requests_user_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brand_requests_user_id ON public.brand_requests USING btree (user_id);


--
-- Name: ix_brands_active; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brands_active ON public.brands USING btree (active);


--
-- Name: ix_brands_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brands_id ON public.brands USING btree (id);


--
-- Name: ix_brands_name; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE UNIQUE INDEX ix_brands_name ON public.brands USING btree (name);


--
-- Name: ix_brands_slug; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE UNIQUE INDEX ix_brands_slug ON public.brands USING btree (slug);


--
-- Name: ix_brands_verified; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_brands_verified ON public.brands USING btree (verified);


--
-- Name: ix_filament_reviews_active; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filament_reviews_active ON public.filament_reviews USING btree (active);


--
-- Name: ix_filament_reviews_filament_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filament_reviews_filament_id ON public.filament_reviews USING btree (filament_id);


--
-- Name: ix_filament_reviews_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filament_reviews_id ON public.filament_reviews USING btree (id);


--
-- Name: ix_filament_reviews_preset_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filament_reviews_preset_id ON public.filament_reviews USING btree (preset_id);


--
-- Name: ix_filament_reviews_user_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filament_reviews_user_id ON public.filament_reviews USING btree (user_id);


--
-- Name: ix_filaments_active; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filaments_active ON public.filaments USING btree (active);


--
-- Name: ix_filaments_brand_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filaments_brand_id ON public.filaments USING btree (brand_id);


--
-- Name: ix_filaments_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filaments_id ON public.filaments USING btree (id);


--
-- Name: ix_filaments_material_type; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filaments_material_type ON public.filaments USING btree (material_type);


--
-- Name: ix_filaments_name; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filaments_name ON public.filaments USING btree (name);


--
-- Name: ix_material_mappings_active; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_material_mappings_active ON public.material_mappings USING btree (active);


--
-- Name: ix_material_mappings_brand_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_material_mappings_brand_id ON public.material_mappings USING btree (brand_id);


--
-- Name: ix_material_mappings_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_material_mappings_id ON public.material_mappings USING btree (id);


--
-- Name: ix_material_mappings_material_type; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_material_mappings_material_type ON public.material_mappings USING btree (material_type);


--
-- Name: ix_material_mappings_priority; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_material_mappings_priority ON public.material_mappings USING btree (priority);


--
-- Name: ix_preset_printers_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_preset_printers_id ON public.preset_printers USING btree (id);


--
-- Name: ix_preset_printers_is_primary; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_preset_printers_is_primary ON public.preset_printers USING btree (is_primary);


--
-- Name: ix_preset_printers_preset_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_preset_printers_preset_id ON public.preset_printers USING btree (preset_id);


--
-- Name: ix_preset_printers_printer_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_preset_printers_printer_id ON public.preset_printers USING btree (printer_id);


--
-- Name: ix_presets_active; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_presets_active ON public.presets USING btree (active);


--
-- Name: ix_presets_filament_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_presets_filament_id ON public.presets USING btree (filament_id);


--
-- Name: ix_presets_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_presets_id ON public.presets USING btree (id);


--
-- Name: ix_presets_is_official; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_presets_is_official ON public.presets USING btree (is_official);


--
-- Name: ix_presets_moderation_status; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_presets_moderation_status ON public.presets USING btree (moderation_status);


--
-- Name: ix_presets_user_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_presets_user_id ON public.presets USING btree (user_id);


--
-- Name: ix_printer_requests_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printer_requests_id ON public.printer_requests USING btree (id);


--
-- Name: ix_printer_requests_slug; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printer_requests_slug ON public.printer_requests USING btree (slug);


--
-- Name: ix_printer_requests_status; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printer_requests_status ON public.printer_requests USING btree (status);


--
-- Name: ix_printer_requests_user_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printer_requests_user_id ON public.printer_requests USING btree (user_id);


--
-- Name: ix_printers_active; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printers_active ON public.printers USING btree (active);


--
-- Name: ix_printers_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printers_id ON public.printers USING btree (id);


--
-- Name: ix_printers_manufacturer; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printers_manufacturer ON public.printers USING btree (manufacturer);


--
-- Name: ix_printers_name; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_printers_name ON public.printers USING btree (name);


--
-- Name: ix_printers_slug; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE UNIQUE INDEX ix_printers_slug ON public.printers USING btree (slug);


--
-- Name: ix_user_saved_presets_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_user_saved_presets_id ON public.user_saved_presets USING btree (id);


--
-- Name: ix_user_saved_presets_preset_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_user_saved_presets_preset_id ON public.user_saved_presets USING btree (preset_id);


--
-- Name: ix_user_saved_presets_user_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_user_saved_presets_user_id ON public.user_saved_presets USING btree (user_id);


--
-- Name: ix_user_saved_presets_user_preset_unique; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE UNIQUE INDEX ix_user_saved_presets_user_preset_unique ON public.user_saved_presets USING btree (user_id, preset_id);


--
-- Name: ix_users_api_key; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE UNIQUE INDEX ix_users_api_key ON public.users USING btree (api_key);


--
-- Name: ix_users_brand_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_users_brand_id ON public.users USING btree (brand_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_printer_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_users_printer_id ON public.users USING btree (printer_id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: brand_requests brand_requests_brand_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.brand_requests
    ADD CONSTRAINT brand_requests_brand_id_fkey FOREIGN KEY (brand_id) REFERENCES public.brands(id);


--
-- Name: brand_requests brand_requests_processed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.brand_requests
    ADD CONSTRAINT brand_requests_processed_by_id_fkey FOREIGN KEY (processed_by_id) REFERENCES public.users(id);


--
-- Name: brand_requests brand_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.brand_requests
    ADD CONSTRAINT brand_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: filament_reviews filament_reviews_filament_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filament_reviews
    ADD CONSTRAINT filament_reviews_filament_id_fkey FOREIGN KEY (filament_id) REFERENCES public.filaments(id);


--
-- Name: filament_reviews filament_reviews_preset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filament_reviews
    ADD CONSTRAINT filament_reviews_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES public.presets(id);


--
-- Name: filament_reviews filament_reviews_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filament_reviews
    ADD CONSTRAINT filament_reviews_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: filaments filaments_brand_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filaments
    ADD CONSTRAINT filaments_brand_id_fkey FOREIGN KEY (brand_id) REFERENCES public.brands(id);


--
-- Name: material_mappings material_mappings_brand_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.material_mappings
    ADD CONSTRAINT material_mappings_brand_id_fkey FOREIGN KEY (brand_id) REFERENCES public.brands(id);


--
-- Name: preset_printers preset_printers_preset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.preset_printers
    ADD CONSTRAINT preset_printers_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES public.presets(id);


--
-- Name: preset_printers preset_printers_printer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.preset_printers
    ADD CONSTRAINT preset_printers_printer_id_fkey FOREIGN KEY (printer_id) REFERENCES public.printers(id);


--
-- Name: presets presets_filament_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.presets
    ADD CONSTRAINT presets_filament_id_fkey FOREIGN KEY (filament_id) REFERENCES public.filaments(id);


--
-- Name: presets presets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.presets
    ADD CONSTRAINT presets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: printer_requests printer_requests_processed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.printer_requests
    ADD CONSTRAINT printer_requests_processed_by_id_fkey FOREIGN KEY (processed_by_id) REFERENCES public.users(id);


--
-- Name: printer_requests printer_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.printer_requests
    ADD CONSTRAINT printer_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: user_saved_presets user_saved_presets_preset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.user_saved_presets
    ADD CONSTRAINT user_saved_presets_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES public.presets(id);


--
-- Name: user_saved_presets user_saved_presets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.user_saved_presets
    ADD CONSTRAINT user_saved_presets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users users_printer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_printer_id_fkey FOREIGN KEY (printer_id) REFERENCES public.printers(id);


--
-- PostgreSQL database dump complete
--

\unrestrict DISllJZP2tIdn1z2NvVt7zuyuLLr3tsWurLxchfRHPimgrbgKqovpMdSodThc8Z

