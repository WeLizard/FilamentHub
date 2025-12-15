"""Add complete wiki system with material properties and troubleshooting

Revision ID: add_wiki_complete
Revises: feedback_table_enum
Create Date: 2025-12-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_wiki_complete'
down_revision: Union[str, None] = 'feedback_table_enum'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    
    # 1. Создаем enum для WikiArticleStatus
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE wikiarticlestatus AS ENUM ('draft', 'pending_review', 'published', 'rejected');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # 2. Создаем enum для PrintProblemSeverity
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE printproblemseverity AS ENUM ('minor', 'moderate', 'major', 'critical');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # 3. Создаем таблицу wiki_categories
    op.create_table(
        'wiki_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_wiki_categories_id', 'wiki_categories', ['id'])
    op.create_index('ix_wiki_categories_name', 'wiki_categories', ['name'], unique=True)
    op.create_index('ix_wiki_categories_slug', 'wiki_categories', ['slug'], unique=True)
    
    # 4. Создаем таблицу wiki_articles
    op.create_table(
        'wiki_articles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=200), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tags', sa.String(length=500), nullable=True),
        sa.Column('author', sa.String(length=100), nullable=True),
        sa.Column('status', postgresql.ENUM('draft', 'pending_review', 'published', 'rejected', name='wikiarticlestatus', create_type=False), nullable=False, server_default='draft'),
        sa.Column('published', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('views', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['wiki_categories.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_wiki_articles_id', 'wiki_articles', ['id'])
    op.create_index('ix_wiki_articles_category_id', 'wiki_articles', ['category_id'])
    op.create_index('ix_wiki_articles_created_by_id', 'wiki_articles', ['created_by_id'])
    op.create_index('ix_wiki_articles_title', 'wiki_articles', ['title'])
    op.create_index('ix_wiki_articles_slug', 'wiki_articles', ['slug'], unique=True)
    op.create_index('ix_wiki_articles_status', 'wiki_articles', ['status'])
    op.create_index('ix_wiki_articles_published', 'wiki_articles', ['published'])
    
    # 5. Создаем таблицу material_properties
    op.create_table(
        'material_properties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('material_type', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        # Physical properties
        sa.Column('density', sa.Float(), nullable=True),
        sa.Column('melting_temp_min', sa.Integer(), nullable=True),
        sa.Column('melting_temp_max', sa.Integer(), nullable=True),
        sa.Column('glass_transition_temp', sa.Integer(), nullable=True),
        sa.Column('shrinkage_percent', sa.Float(), nullable=True),
        sa.Column('tensile_strength_mpa', sa.Float(), nullable=True),
        sa.Column('flexural_strength_mpa', sa.Float(), nullable=True),
        sa.Column('elongation_at_break_percent', sa.Float(), nullable=True),
        sa.Column('elastic_modulus_mpa', sa.Float(), nullable=True),
        sa.Column('hardness_shore', sa.String(length=20), nullable=True),
        # Chemical properties
        sa.Column('chemical_formula', sa.String(length=100), nullable=True),
        sa.Column('chemical_resistance', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('solvents', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('toxicity_rating', sa.String(length=20), nullable=True),
        sa.Column('fumes_info', sa.Text(), nullable=True),
        sa.Column('biodegradable', sa.Boolean(), nullable=True),
        sa.Column('food_safe', sa.Boolean(), nullable=True),
        # Processing
        sa.Column('adhesives', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('post_processing', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('paint_compatibility', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('heat_treatment', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        # Applications
        sa.Column('recommended_uses', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('not_recommended_uses', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('typical_applications', sa.Text(), nullable=True),
        # Printing
        sa.Column('print_temp_range', sa.String(length=50), nullable=True),
        sa.Column('bed_temp_range', sa.String(length=50), nullable=True),
        sa.Column('print_speed_range', sa.String(length=50), nullable=True),
        sa.Column('requires_enclosure', sa.Boolean(), nullable=True),
        sa.Column('warping_tendency', sa.String(length=20), nullable=True),
        sa.Column('stringing_tendency', sa.String(length=20), nullable=True),
        sa.Column('layer_adhesion', sa.String(length=20), nullable=True),
        sa.Column('support_difficulty', sa.String(length=20), nullable=True),
        # Metadata
        sa.Column('data_sources', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('verified_by_id', sa.Integer(), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['verified_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_material_properties_material_type', 'material_properties', ['material_type'], unique=True)
    op.create_index('ix_material_properties_verified', 'material_properties', ['verified'])
    op.create_index('ix_material_properties_created_by_id', 'material_properties', ['created_by_id'])
    
    # 6. Создаем таблицу print_problems
    op.create_table(
        'print_problems',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=200), nullable=False),
        sa.Column('aliases', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('severity', postgresql.ENUM('minor', 'moderate', 'major', 'critical', name='printproblemseverity', create_type=False), nullable=False, server_default='moderate'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('example_images', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('visual_symptoms', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('causes', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('common_materials', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('solutions', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('quick_fixes', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('prevention_tips', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('slicer_settings', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('related_problems', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('tags', sa.String(length=500), nullable=True),
        sa.Column('views', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('helpful_votes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('published', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.Column('verified_by_id', sa.Integer(), nullable=True),
        sa.Column('order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['verified_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_print_problems_name', 'print_problems', ['name'])
    op.create_index('ix_print_problems_slug', 'print_problems', ['slug'], unique=True)
    op.create_index('ix_print_problems_severity', 'print_problems', ['severity'])
    op.create_index('ix_print_problems_published', 'print_problems', ['published'])
    op.create_index('ix_print_problems_verified', 'print_problems', ['verified'])
    op.create_index('ix_print_problems_created_by_id', 'print_problems', ['created_by_id'])
    
    # 7. Добавляем поле can_edit_wiki в users
    op.add_column('users', sa.Column('can_edit_wiki', sa.Boolean(), nullable=False, server_default='false'))
    op.create_index('ix_users_can_edit_wiki', 'users', ['can_edit_wiki'])


def downgrade() -> None:
    """Downgrade database schema."""
    
    # Удаляем поле из users
    op.drop_index('ix_users_can_edit_wiki', table_name='users')
    op.drop_column('users', 'can_edit_wiki')
    
    # Удаляем print_problems
    op.drop_index('ix_print_problems_created_by_id', table_name='print_problems')
    op.drop_index('ix_print_problems_verified', table_name='print_problems')
    op.drop_index('ix_print_problems_published', table_name='print_problems')
    op.drop_index('ix_print_problems_severity', table_name='print_problems')
    op.drop_index('ix_print_problems_slug', table_name='print_problems')
    op.drop_index('ix_print_problems_name', table_name='print_problems')
    op.drop_table('print_problems')
    
    # Удаляем material_properties
    op.drop_index('ix_material_properties_created_by_id', table_name='material_properties')
    op.drop_index('ix_material_properties_verified', table_name='material_properties')
    op.drop_index('ix_material_properties_material_type', table_name='material_properties')
    op.drop_table('material_properties')
    
    # Удаляем wiki_articles
    op.drop_index('ix_wiki_articles_published', table_name='wiki_articles')
    op.drop_index('ix_wiki_articles_status', table_name='wiki_articles')
    op.drop_index('ix_wiki_articles_slug', table_name='wiki_articles')
    op.drop_index('ix_wiki_articles_title', table_name='wiki_articles')
    op.drop_index('ix_wiki_articles_created_by_id', table_name='wiki_articles')
    op.drop_index('ix_wiki_articles_category_id', table_name='wiki_articles')
    op.drop_index('ix_wiki_articles_id', table_name='wiki_articles')
    op.drop_table('wiki_articles')
    
    # Удаляем wiki_categories
    op.drop_index('ix_wiki_categories_slug', table_name='wiki_categories')
    op.drop_index('ix_wiki_categories_name', table_name='wiki_categories')
    op.drop_index('ix_wiki_categories_id', table_name='wiki_categories')
    op.drop_table('wiki_categories')
    
    # Удаляем enums
    op.execute("DROP TYPE IF EXISTS printproblemseverity")
    op.execute("DROP TYPE IF EXISTS wikiarticlestatus")

