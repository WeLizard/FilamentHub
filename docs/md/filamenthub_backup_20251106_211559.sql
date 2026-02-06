--
-- PostgreSQL database dump
--

\restrict hKfURt1sXu60mz9WhbBCzikt0O3dbMSAs2E4UikG5xNaIlDvXgj0bBt2IPH6q1A

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
-- Name: notificationtype; Type: TYPE; Schema: public; Owner: filamenthub
--

CREATE TYPE public.notificationtype AS ENUM (
    'preset_updated',
    'preset_deleted',
    'brand_verified',
    'brand_request_approved',
    'brand_request_rejected'
);


ALTER TYPE public.notificationtype OWNER TO filamenthub;

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
-- Name: alembic_migration_history; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.alembic_migration_history (
    revision character varying(50) NOT NULL,
    applied_at timestamp without time zone DEFAULT now() NOT NULL,
    applied_by character varying(255),
    downgraded_at timestamp without time zone,
    downgraded_by character varying(255)
);


ALTER TABLE public.alembic_migration_history OWNER TO filamenthub;

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
    request_type character varying(20) NOT NULL,
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
    status character varying(20) DEFAULT 'pending'::public.brandrequeststatus NOT NULL,
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
    visual_settings json,
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
-- Name: notifications; Type: TABLE; Schema: public; Owner: filamenthub
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer NOT NULL,
    type public.notificationtype NOT NULL,
    title character varying(200) NOT NULL,
    message text NOT NULL,
    link character varying(500),
    extra_data json,
    read boolean DEFAULT false NOT NULL,
    read_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.notifications OWNER TO filamenthub;

--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: filamenthub
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notifications_id_seq OWNER TO filamenthub;

--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: filamenthub
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


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
    orcaslicer_settings json,
    success_rate double precision,
    is_weighted boolean DEFAULT false NOT NULL
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
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


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
-- Data for Name: alembic_migration_history; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.alembic_migration_history (revision, applied_at, applied_by, downgraded_at, downgraded_by) FROM stdin;
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.alembic_version (version_num) FROM stdin;
add_notifications
\.


--
-- Data for Name: brand_requests; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.brand_requests (id, user_id, request_type, brand_id, new_brand_name, new_brand_slug, new_brand_description, new_brand_website, message, proof_text, company_email, company_website, social_media_urls, proof_files, status, processed_by_id, processed_at, rejection_reason, created_at, updated_at) FROM stdin;
12	5	join	1	\N	\N	\N	\N	\N	123	321@example.ru	\N	\N	[{"path": "brand_requests/12/eeb557e1d60b4046959c7a96ccc4d9c1.jpg", "name": "\\u0421\\u043d\\u0438\\u043c\\u043e\\u043a.JPG"}]	approved	6	2025-11-06 20:02:09.434736	\N	2025-11-06 20:02:03.094694	2025-11-06 20:02:09.431876
\.


--
-- Data for Name: brands; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.brands (id, name, slug, description, website, logo_url, verified, active, created_at, updated_at) FROM stdin;
6	TestBrand - Новый производитель	testbrand	\N	\N	\N	f	t	2025-11-02 23:21:09.440381	2025-11-02 23:21:09.440381
7	RORI	rori	\N	\N	\N	f	t	2025-11-03 11:38:19.89248	2025-11-03 11:38:19.89248
8	KRYAKER	kryaker	\N	\N	\N	f	t	2025-11-03 12:28:03.65723	2025-11-03 12:28:03.65723
3	eSUN	esun	Профессиональные материалы для 3D-печати	https://www.esun3d.com	\N	f	t	2025-10-31 14:57:35.516101	2025-11-03 21:31:32.246335
2	Sunlu	sunlu	Популярный китайский бренд	https://www.sunlu.com	\N	f	t	2025-10-31 14:57:35.516101	2025-11-03 21:31:35.678504
4	Polymaker	polymaker	Премиум материалы из Китая	https://polymaker.com	\N	f	t	2025-10-31 14:57:35.516101	2025-11-03 21:31:39.533726
1	Bestfilament	bestfilament	Российский производитель качественного пластика	https://bestfilament.ru	\N	t	t	2025-10-31 14:57:35.516101	2025-11-03 21:32:50.669261
\.


--
-- Data for Name: filament_reviews; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.filament_reviews (id, filament_id, user_id, success, rating, comment, printer_model, active, created_at, updated_at, preset_id) FROM stdin;
1	3	5	f	2	Ну и гавно ваш пресет	Ендерь 3 Прё макс	t	2025-11-06 20:29:38.713724	2025-11-06 20:29:38.713724	3
2	3	6	t	4	Ну в целом нормас работает	Bambu Lab A1	t	2025-11-06 20:30:55.606051	2025-11-06 20:30:55.606051	3
\.


--
-- Data for Name: filaments; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.filaments (id, brand_id, name, material_type, color_name, color_hex, diameter, density, price_per_kg, spool_weight, description, active, created_at, updated_at, views_count, scans_count, visual_settings, qr_code) FROM stdin;
1	1	PLA Red	PLA	Red	#FF0000	1.75	1.24	800	1000	Красный PLA от Bestfilament	t	2025-10-31 14:57:35.516101	2025-10-31 14:57:35.516101	0	0	\N	\N
2	1	PLA Blue	PLA	Blue	#0000FF	1.75	1.24	800	1000	Синий PLA от Bestfilament	t	2025-10-31 14:57:35.516101	2025-10-31 14:57:35.516101	0	0	\N	\N
3	2	PETG Black	PETG	Black	#000000	1.75	1.27	950	1000	Черный PETG от Sunlu	t	2025-10-31 14:57:35.516101	2025-10-31 14:57:35.516101	0	0	\N	\N
4	2	PLA+ White	PLA	White	#FFFFFF	1.75	1.24	850	1000	Белый PLA+ от Sunlu	t	2025-10-31 14:57:35.516101	2025-10-31 14:57:35.516101	0	0	\N	\N
5	3	TPU 95A	TPU	Transparent	#FFFFFF	1.75	1.2	1800	500	Прозрачный TPU от eSUN	t	2025-10-31 14:57:35.516101	2025-10-31 14:57:35.516101	0	0	\N	\N
6	4	PolyTerra PLA	PLA	Natural	#F5E6D3	1.75	1.24	1200	1000	Экологичный PLA от Polymaker	t	2025-10-31 14:57:35.516101	2025-10-31 14:57:35.516101	0	0	\N	\N
8	4	PolyTerra PLA Green	PLA	Green	#00ff00	1.75	1.24	\N	\N	\N	t	2025-11-02 23:01:23.071986	2025-11-02 23:01:23.071986	0	0	\N	\N
9	6	TestFilament PLA Pro	PLA	Синий	#0000FF	1.75	1.24	\N	\N	\N	t	2025-11-02 23:21:09.70431	2025-11-02 23:21:09.70431	0	0	\N	\N
10	7	PP PLUS	PP+	Серый	#808080	1.75	1.24	\N	\N	\N	t	2025-11-03 11:38:20.13995	2025-11-03 11:38:20.13995	0	0	\N	\N
11	8	GAVNO-300	KRYA	Коричневый	#352c2c	1.75	1.24	\N	\N	\N	t	2025-11-03 12:28:03.981012	2025-11-03 12:28:03.981012	0	0	\N	\N
12	8	PLA  Silk	PLA	Золотой	#C3B33C	1.75	1.24	\N	\N	\N	t	2025-11-03 18:51:22.407171	2025-11-03 18:51:22.407171	0	0	{"color_type": "single", "colors": ["#C3B33C"], "finish": "matte", "filler": "metallic", "transparency": false}	\N
7	1	PETG ZERO	PETG	Серобуромалиновый	#977168	1.75	1.24	1200	3000	\N	t	2025-11-01 14:11:02.799073	2025-11-04 18:00:48.260665	0	0	\N	\N
13	1	PETGIO	PETG	Серебряный	#787878	1.75	1.24	1200	1000	\N	t	2025-11-04 19:07:09.454199	2025-11-04 19:07:09.454199	0	0	{"color_type": "single", "colors": ["#787878"], "finish": "matte", "filler": "metallic", "transparency": false}	FHUB-D
\.


--
-- Data for Name: material_mappings; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.material_mappings (id, material_type, orcaslicer_preset, priority, brand_id, description, active, created_at, updated_at) FROM stdin;
1	PLA	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PLA' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
2	ABS	Generic ABS @System	manual	\N	Начальный маппинг для материала 'ABS' → 'Generic ABS @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
3	PETG	Generic PETG @System	manual	\N	Начальный маппинг для материала 'PETG' → 'Generic PETG @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
4	PET	Generic PETG @System	manual	\N	Начальный маппинг для материала 'PET' → 'Generic PETG @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
5	TPU	Generic TPU @System	manual	\N	Начальный маппинг для материала 'TPU' → 'Generic TPU @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
6	ASA	Generic ASA @System	manual	\N	Начальный маппинг для материала 'ASA' → 'Generic ASA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
7	PC	Generic PC @System	manual	\N	Начальный маппинг для материала 'PC' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
8	PA	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
9	PVA	Generic PVA @System	manual	\N	Начальный маппинг для материала 'PVA' → 'Generic PVA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
10	HIPS	Generic ABS @System	manual	\N	Начальный маппинг для материала 'HIPS' → 'Generic ABS @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
11	PP	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PP' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
12	POM	Generic PLA @System	manual	\N	Начальный маппинг для материала 'POM' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
13	PET-CF	Generic PETG @System	manual	\N	Начальный маппинг для материала 'PET-CF' → 'Generic PETG @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
14	PETG-CF	Generic PETG @System	manual	\N	Начальный маппинг для материала 'PETG-CF' → 'Generic PETG @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
15	PLA-CF	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PLA-CF' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
16	ABS-CF	Generic ABS @System	manual	\N	Начальный маппинг для материала 'ABS-CF' → 'Generic ABS @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
17	ASA-CF	Generic ASA @System	manual	\N	Начальный маппинг для материала 'ASA-CF' → 'Generic ASA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
18	PC-CF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PC-CF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
19	PA-CF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA-CF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
20	PP-CF	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PP-CF' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
21	ABS-GF	Generic ABS @System	manual	\N	Начальный маппинг для материала 'ABS-GF' → 'Generic ABS @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
22	ASA-GF	Generic ASA @System	manual	\N	Начальный маппинг для материала 'ASA-GF' → 'Generic ASA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
23	PA-GF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA-GF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
24	PET-GF	Generic PETG @System	manual	\N	Начальный маппинг для материала 'PET-GF' → 'Generic PETG @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
25	PETG-GF	Generic PETG @System	manual	\N	Начальный маппинг для материала 'PETG-GF' → 'Generic PETG @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
26	PC-PBT	Generic PC @System	manual	\N	Начальный маппинг для материала 'PC-PBT' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
27	PA6	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA6' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
28	PA11	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA11' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
29	PA12	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA12' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
30	PAHT	Generic PA @System	manual	\N	Начальный маппинг для материала 'PAHT' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
31	PA6-CF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA6-CF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
32	PA11-CF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA11-CF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
33	PA12-CF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA12-CF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
34	PAHT-CF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PAHT-CF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
35	PA6-GF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA6-GF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
36	PA11-GF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA11-GF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
37	PA12-GF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PA12-GF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
38	PAHT-GF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PAHT-GF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
39	PEI	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEI' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
40	PEI-1010	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEI-1010' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
41	PEI-9085	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEI-9085' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
42	PEI-1010-CF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEI-1010-CF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
43	PEI-9085-CF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEI-9085-CF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
44	PEI-1010-GF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEI-1010-GF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
45	PEI-9085-GF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEI-9085-GF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
46	PEEK	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEEK' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
47	PEEK-CF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEEK-CF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
48	PEEK-GF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEEK-GF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
49	PEKK	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEKK' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
50	PEKK-CF	Generic PC @System	manual	\N	Начальный маппинг для материала 'PEKK-CF' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
51	PES	Generic PC @System	manual	\N	Начальный маппинг для материала 'PES' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
52	PPS	Generic PC @System	manual	\N	Начальный маппинг для материала 'PPS' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
53	PPSU	Generic PC @System	manual	\N	Начальный маппинг для материала 'PPSU' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
54	PSU	Generic PC @System	manual	\N	Начальный маппинг для материала 'PSU' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
55	TPI	Generic TPU @System	manual	\N	Начальный маппинг для материала 'TPI' → 'Generic TPU @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
56	PI	Generic PC @System	manual	\N	Начальный маппинг для материала 'PI' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
57	FLEX	Generic TPU @System	manual	\N	Начальный маппинг для материала 'FLEX' → 'Generic TPU @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
58	PCL	Generic TPU @System	manual	\N	Начальный маппинг для материала 'PCL' → 'Generic TPU @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
59	BVOH	Generic PVA @System	manual	\N	Начальный маппинг для материала 'BVOH' → 'Generic PVA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
60	PVB	Generic PVA @System	manual	\N	Начальный маппинг для материала 'PVB' → 'Generic PVA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
61	ASA-AERO	Generic ASA @System	manual	\N	Начальный маппинг для материала 'ASA-AERO' → 'Generic ASA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
62	PLA-AERO	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PLA-AERO' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
63	PC-ABS	Generic PC @System	manual	\N	Начальный маппинг для материала 'PC-ABS' → 'Generic PC @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
64	PCTG	Generic PETG @System	manual	\N	Начальный маппинг для материала 'PCTG' → 'Generic PETG @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
65	PHA	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PHA' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
66	PE	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PE' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
67	PE-CF	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PE-CF' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
68	PE-GF	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PE-GF' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
69	PVDF	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PVDF' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
70	SBS	Generic PLA @System	manual	\N	Начальный маппинг для материала 'SBS' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
71	PPA	Generic PA @System	manual	\N	Начальный маппинг для материала 'PPA' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
72	PPA-CF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PPA-CF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
73	PPA-GF	Generic PA @System	manual	\N	Начальный маппинг для материала 'PPA-GF' → 'Generic PA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
74	EVA	Generic TPU @System	manual	\N	Начальный маппинг для материала 'EVA' → 'Generic TPU @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
75	PLA+	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PLA+' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
76	PLA PRO	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PLA PRO' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
77	PLA PRO+	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PLA PRO+' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
78	PLA MAX	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PLA MAX' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
79	PP+	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PP+' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
80	PP PLUS	Generic PLA @System	manual	\N	Начальный маппинг для материала 'PP PLUS' → 'Generic PLA @System'	t	2025-11-03 12:26:42.686711+00	2025-11-03 12:26:42.686711+00
81	KRYA	fdm_filament_common	automatic	\N	Автоматически создан для материала 'KRYA' → 'fdm_filament_common'	t	2025-11-03 12:28:03.988108+00	2025-11-03 12:28:03.988108+00
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.notifications (id, user_id, type, title, message, link, extra_data, read, read_at, created_at) FROM stdin;
1	5	brand_request_rejected	Заявка на бренд отклонена	Ваша заявка на присоединение к бренду "Polymaker" была отклонена. Причина: 21v3	\N	{"brand_name": "Polymaker", "reason": "21v3"}	f	\N	2025-11-06 19:45:10.507671+00
2	5	brand_request_approved	Заявка на бренд одобрена	Ваша заявка на присоединение к бренду "Bestfilament" была одобрена.	/brands/1	{"brand_id": 1}	f	\N	2025-11-06 20:02:09.438577+00
\.


--
-- Data for Name: preset_printers; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.preset_printers (id, preset_id, printer_id, is_primary, created_at, updated_at) FROM stdin;
4	20	1	t	2025-11-06 17:01:40.869649+00	2025-11-06 17:01:40.869649+00
5	19	1	t	2025-11-06 18:11:55.698281+00	2025-11-06 18:11:55.698281+00
\.


--
-- Data for Name: presets; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.presets (id, filament_id, name, description, is_official, extruder_temp, bed_temp, print_speed, travel_speed, layer_height, first_layer_height, flow_rate, fan_speed, retraction_length, retraction_speed, rating, usage_count, active, created_at, updated_at, moderation_status, moderation_reason, moderated_by, moderated_at, user_id, orcaslicer_settings, success_rate, is_weighted) FROM stdin;
3	3	Официальный пресет Sunlu	Рекомендуемые настройки от производителя	t	240	80	40	150	0.2	0.3	98	50	6	40	3	312	t	2025-10-31 18:13:54.544751	2025-11-06 20:30:55.616524	approved	\N	\N	\N	\N	{}	50	f
1	1	Официальный пресет Bestfilament	Рекомендуемые настройки от производителя	t	200	60	50	150	0.2	0.3	100	100	5	45	4.8	245	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
2	2	Официальный пресет Bestfilament	Рекомендуемые настройки от производителя	t	200	60	50	150	0.2	0.3	100	100	5	45	4.8	189	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
4	4	Официальный пресет Sunlu	Рекомендуемые настройки от производителя	t	210	60	55	150	0.2	0.3	100	100	5	45	4.8	198	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
5	5	Официальный пресет eSUN	Рекомендуемые настройки от производителя	t	230	50	25	100	0.2	0.3	95	0	3	30	4.7	156	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
6	6	Официальный пресет Polymaker	Рекомендуемые настройки от производителя	t	205	60	50	150	0.2	0.3	100	100	5	45	4.8	234	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
7	1	3D_Guru	Проверенная настройка для Ender 3 Pro	f	195	60	45	150	0.2	0.3	100	100	5	45	4.8	124	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
10	7	PETG ZERO	КРЯ РКЯ	f	250	60	50	150	0.2	0.3	100	100	5	45	\N	0	t	2025-11-01 14:11:02.817536	2025-11-01 14:11:02.817536	approved	\N	\N	\N	4	{}	\N	f
8	1	PrintMaster	Оптимизированная настройка для высокой скорости	f	205	55	55	150	0.2	0.3	100	100	5	45	4.5	87	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
9	3	PETG_Pro	Оптимальные настройки для прочности	f	235	85	35	150	0.2	0.3	98	50	6	40	4.9	156	t	2025-10-31 18:13:54.544751	2025-10-31 18:13:54.544751	approved	\N	\N	\N	\N	{}	\N	f
13	1	Тестовый пресет с расширенными параметрами	Пресет создан для тестирования нового функционала с first_layer_height и orcaslicer_settings	f	205	60	50	150	0.2	0.3	100	100	5	45	\N	0	t	2025-11-02 22:55:31.21047	2025-11-02 22:55:31.21047	approved	\N	\N	\N	\N	{"pressure_advance": ["0.05"], "nozzle_temperature_range_low": ["195"], "filament_max_volumetric_speed": ["12"], "nozzle_temperature_range_high": ["215"]}	\N	f
14	8	PolyTerra Green Standard	Оптимальные настройки для PolyTerra PLA Green	f	200	60	50	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-02 23:01:23.408713	2025-11-02 23:01:23.408713	pending	\N	\N	\N	6	{"default_filament_colour": ["#00ff00"]}	\N	f
15	9	ТЕСТПРЕСЕТ	Тестовый пресет со всеми заполненными полями и галочками	f	210	70	55	160	0.25	0.3	105	90	6	50	\N	0	t	2025-11-02 23:21:09.779499	2025-11-02 23:37:26.133193	pending	\N	\N	\N	6	{"nozzle_temperature_range_low": ["190"], "nozzle_temperature_range_high": ["230"], "idle_temperature": ["180"], "temperature_vitrification": ["60"], "chamber_temperature": ["45"], "activate_chamber_temp_control": ["1"], "filament_max_volumetric_speed": ["15"], "filament_adaptive_volumetric_speed": ["1"], "default_filament_colour": ["#0000FF"], "filament_deretraction_speed": ["52"], "filament_retract_before_wipe": ["55%"], "filament_retract_when_changing_layer": ["1"], "filament_retract_restart_extra": ["1"], "filament_z_hop": ["2"], "filament_z_hop_types": ["Normal"], "filament_retract_lift_above": ["5"], "filament_retract_lift_enforce": ["TopOnly"], "filament_wipe": ["1"], "filament_wipe_distance": ["1"], "pressure_advance": ["0.05"], "enable_pressure_advance": ["1"], "adaptive_pressure_advance": ["1"], "adaptive_pressure_advance_bridges": ["1"], "adaptive_pressure_advance_overhangs": ["1"], "fan_min_speed": ["50"], "fan_max_speed": ["100"], "fan_cooling_layer_time": ["35"], "slow_down_layer_time": ["2"], "reduce_fan_stop_start_freq": ["1"], "full_fan_speed_layer": ["2"], "close_fan_the_first_x_layers": ["3"], "slow_down_for_layer_cooling": ["1"], "ironing_fan_speed": ["1"], "additional_cooling_fan_speed": ["25"], "during_print_exhaust_fan_speed": ["55"], "complete_print_exhaust_fan_speed": ["25"], "activate_air_filtration": ["1"], "long_retractions_when_ec": ["1"], "retraction_distances_when_ec": ["5"], "filament_start_gcode": ["{filament_extruder_id}{zhop}{e_retracted[]}{e_restart_extra[]}{first_layer_height}{bed_temperature[]}"], "filament_end_gcode": ["{zhop}{position[]}{e_position[]}{first_layer_print_convex_hull[]}{first_layer_print_min[]}"], "filament_multitool_ramming_flow": ["2"], "filament_multitool_ramming_volume": ["2"], "filament_toolchange_delay": ["5"], "filament_loading_speed": ["25"], "filament_loading_speed_start": ["3"], "filament_unloading_speed_start": ["12"], "filament_change_length": ["1"], "filament_cooling_initial_speed": ["2"], "filament_cooling_final_speed": ["2"], "filament_cooling_moves": ["4"], "filament_stamping_distance": ["5"], "filament_stamping_loading_speed": ["1"], "filament_minimal_purge_on_wipe_tower": ["15"], "filament_notes": ["\\u043a\\u0440\\u044f"]}	\N	f
16	10	100проц печать	\N	f	200	60	50	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-03 11:38:20.214501	2025-11-03 11:38:20.214501	pending	\N	\N	\N	6	{"default_filament_colour": ["#808080"]}	\N	f
17	11	ТЫЛох	213м123м	f	200	60	50	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-03 12:28:04.335034	2025-11-03 12:28:04.335034	pending	\N	\N	\N	6	{"default_filament_colour": ["#352c2c"]}	\N	f
18	12	Золотище	\N	f	200	60	50	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-03 18:51:22.742029	2025-11-03 18:51:22.742029	pending	\N	\N	\N	6	{"nozzle_temperature_initial_layer": ["235"], "idle_temperature": ["200"], "filament_shrink": ["100%"], "filament_shrinkage_compensation_z": ["100%"], "default_filament_colour": ["#C3B33C"], "close_fan_the_first_x_layers": ["2"], "overhang_fan_speed": ["70"]}	\N	f
20	1	e12v312vмм	213v123	f	210	60	80	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-06 16:58:14.152672	2025-11-06 17:01:40.869649	approved	\N	\N	\N	5	{"nozzle_temperature_range_low": ["190"], "nozzle_temperature_range_high": ["230"], "nozzle_temperature_initial_layer": ["205"], "idle_temperature": ["150"], "chamber_temperature": ["0"], "filament_max_volumetric_speed": ["15"], "filament_shrink": ["100%"], "filament_shrinkage_compensation_z": ["100%"], "default_filament_colour": ["#FF0000"], "pressure_advance": ["0.02"], "enable_pressure_advance": ["1"], "fan_min_speed": ["20"], "fan_max_speed": ["100"], "close_fan_the_first_x_layers": ["1"], "overhang_fan_speed": ["100"]}	\N	f
21	1	PLA Red Gen	Генеративно вычисляется на основе 5 пресетов для этого материала	f	200.1	59.1	50.4	150	0.2	0.3	100	100	5	45	\N	0	t	2025-11-06 16:58:14.211514	2025-11-06 17:01:40.929102	approved	\N	\N	\N	\N	\N	\N	t
19	2	Тестовый	Крякря	f	210	60	80	150	0.2	\N	100	100	5	45	\N	0	t	2025-11-06 16:11:09.051387	2025-11-06 18:11:55.698281	approved	\N	\N	\N	5	{"nozzle_temperature_range_low": ["190"], "nozzle_temperature_range_high": ["230"], "nozzle_temperature_initial_layer": ["205"], "idle_temperature": ["150"], "chamber_temperature": ["0"], "filament_max_volumetric_speed": ["15"], "filament_shrink": ["100%"], "filament_shrinkage_compensation_z": ["100%"], "default_filament_colour": ["#0000FF"], "pressure_advance": ["0.02"], "fan_min_speed": ["20"], "fan_max_speed": ["100"], "close_fan_the_first_x_layers": ["1"], "overhang_fan_speed": ["100"]}	\N	f
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
1	Бамбу	Kuz	Бамбу 23	bambu	300	300	350	0.4	300	150	собрал на коленке	\N	t	2025-11-06 15:40:03.305693	2025-11-06 15:40:03.305693
\.


--
-- Data for Name: user_saved_presets; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.user_saved_presets (id, user_id, preset_id, saved_at) FROM stdin;
3	4	3	2025-11-01 14:09:48.530089+00
4	4	7	2025-11-01 14:09:50.888155+00
5	4	2	2025-11-01 14:11:42.825915+00
7	6	1	2025-11-02 22:32:51.526316+00
8	6	7	2025-11-02 22:32:54.512872+00
9	6	3	2025-11-03 20:10:36.631576+00
10	6	10	2025-11-06 15:11:15.752461+00
11	6	2	2025-11-06 15:11:25.297101+00
12	6	4	2025-11-06 15:11:30.718995+00
13	6	6	2025-11-06 15:11:37.153055+00
14	5	21	2025-11-06 17:01:57.632106+00
15	5	6	2025-11-06 18:12:21.11339+00
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: filamenthub
--

COPY public.users (id, email, username, password_hash, role, api_key, full_name, bio, active, email_verified, brand_id, created_at, updated_at, last_login, printer_id) FROM stdin;
1	testuser@example.com	testuser123	$2b$12$79i2qRn1O3XfCriHH1JC6.RQCPqocDaqpF3plWA8eS/9Vb/NxT9H2	user	\N	\N	\N	t	f	\N	2025-10-31 19:35:45.255905+00	2025-10-31 19:37:10.891476+00	2025-10-31 19:37:11.078992+00	\N
2	testuser2@example.com	testuser2	$2b$12$5GzYF4tuvD5.Jegcvrwd9eGpve1zmKiv3H3Row4WIuLQxgaXzapCu	user	\N	\N	\N	t	f	\N	2025-10-31 20:19:38.850719+00	2025-10-31 20:19:38.850719+00	\N	\N
3	testuser3@example.com	testuser3	$2b$12$gC3V1P8J1udvaIb3DXtTTeXg7MKQodEx45xzykF.XjRGhIzrdO.aK	user	\N	\N	\N	t	f	\N	2025-10-31 20:20:27.338255+00	2025-10-31 20:20:27.56671+00	2025-10-31 20:20:27.755016+00	\N
5	321@example.ru	REC	$2b$12$LfbpUGqQjN2gnk1NwobzEOQc/j2O/OVrzQV54ppbKB8FtdKRlCZwW	user	\N	\N	\N	t	f	1	2025-11-01 14:14:32.631047+00	2025-11-06 20:02:09.431876+00	2025-11-06 20:01:50.701848+00	\N
4	123@example.ru	123	$2b$12$YQUCLdUj0tbW0c9joP7LQuNRPR10QpL3QT9JBWy9H2tGK3RAsxTZK	user	\N	\N	\N	t	f	\N	2025-11-01 14:03:15.210367+00	2025-11-01 15:21:04.044928+00	2025-11-01 15:21:04.244538+00	\N
7	brandtest2@test.com	brandtest2	$2b$12$RXlpTTZe7jrf3XkdD28GJ.p2R8QXswHwQKIeqKUwsf56MF9qoLxP.	user	\N	\N	\N	t	f	\N	2025-11-01 23:44:02.456341+00	2025-11-06 19:31:28.699483+00	\N	\N
6	admin@filamenthub.ru	admin	$2b$12$TTLAi0CoXXF1Intw9IQdiexGSBYB8mjGZojCFMFKcdwOglNarb1TK	admin	\N	\N	\N	t	t	\N	2025-11-01 23:38:43.694974+00	2025-11-06 19:44:46.97167+00	2025-11-06 19:44:47.15866+00	\N
\.


--
-- Name: brand_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.brand_requests_id_seq', 12, true);


--
-- Name: brands_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.brands_id_seq', 8, true);


--
-- Name: filament_reviews_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.filament_reviews_id_seq', 2, true);


--
-- Name: filaments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.filaments_id_seq', 13, true);


--
-- Name: material_mappings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.material_mappings_id_seq', 81, true);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.notifications_id_seq', 2, true);


--
-- Name: preset_printers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.preset_printers_id_seq', 5, true);


--
-- Name: presets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.presets_id_seq', 21, true);


--
-- Name: printer_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.printer_requests_id_seq', 1, false);


--
-- Name: printers_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.printers_id_seq', 1, true);


--
-- Name: user_saved_presets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.user_saved_presets_id_seq', 15, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: filamenthub
--

SELECT pg_catalog.setval('public.users_id_seq', 7, true);


--
-- Name: alembic_migration_history alembic_migration_history_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.alembic_migration_history
    ADD CONSTRAINT alembic_migration_history_pkey PRIMARY KEY (revision);


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
-- Name: filaments filaments_qr_code_key; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.filaments
    ADD CONSTRAINT filaments_qr_code_key UNIQUE (qr_code);


--
-- Name: material_mappings material_mappings_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.material_mappings
    ADD CONSTRAINT material_mappings_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


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
-- Name: ix_filaments_qr_code; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_filaments_qr_code ON public.filaments USING btree (qr_code);


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
-- Name: ix_notifications_created_at; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_notifications_created_at ON public.notifications USING btree (created_at);


--
-- Name: ix_notifications_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_notifications_id ON public.notifications USING btree (id);


--
-- Name: ix_notifications_read; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_notifications_read ON public.notifications USING btree (read);


--
-- Name: ix_notifications_type; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_notifications_type ON public.notifications USING btree (type);


--
-- Name: ix_notifications_user_id; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);


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
-- Name: ix_presets_is_weighted; Type: INDEX; Schema: public; Owner: filamenthub
--

CREATE INDEX ix_presets_is_weighted ON public.presets USING btree (is_weighted);


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
    ADD CONSTRAINT filament_reviews_preset_id_fkey FOREIGN KEY (preset_id) REFERENCES public.presets(id) ON DELETE SET NULL;


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
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: filamenthub
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


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

\unrestrict hKfURt1sXu60mz9WhbBCzikt0O3dbMSAs2E4UikG5xNaIlDvXgj0bBt2IPH6q1A

