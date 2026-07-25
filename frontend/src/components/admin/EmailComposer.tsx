import { useCallback, useEffect, useRef, useState } from 'react';
import { EditorContent, useEditor, type Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import {
  Bold,
  FileText,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Paperclip,
  Quote,
  Redo2,
  Undo2,
  Underline,
  X,
} from 'lucide-react';
import { useDropzone } from 'react-dropzone';
import { useTranslation } from 'react-i18next';
import { toast } from '../Toast';

const MAX_ATTACHMENTS = 10;
const MAX_ATTACHMENTS_BYTES = 15 * 1024 * 1024;

const ACCEPTED_ATTACHMENTS = {
  'application/msword': ['.doc'],
  'application/pdf': ['.pdf'],
  'application/vnd.ms-excel': ['.xls'],
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': ['.pptx'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
  'text/csv': ['.csv'],
  'text/plain': ['.txt'],
};

export interface EmailComposerValue {
  text: string;
  html: string;
  attachments: File[];
}

interface EmailComposerProps {
  id: string;
  onChange: (value: EmailComposerValue) => void;
  disabled?: boolean;
  resetKey?: number;
}

const formatBytes = (value: number, locale: string): string => {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / 1024)} KB`;
  }
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value / (1024 * 1024))} MB`;
};

function ToolbarButton({
  active = false,
  disabled = false,
  label,
  onClick,
  children,
}: {
  active?: boolean;
  disabled?: boolean;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
      className={`grid h-8 w-8 place-items-center rounded-lg transition ${
        active
          ? 'bg-cyan-400/20 text-cyan-200'
          : 'text-gray-400 hover:bg-white/10 hover:text-white'
      } disabled:cursor-not-allowed disabled:opacity-35`}
    >
      {children}
    </button>
  );
}

export function EmailComposer({
  id,
  onChange,
  disabled = false,
  resetKey = 0,
}: EmailComposerProps) {
  const { t, i18n } = useTranslation();
  const [attachments, setAttachments] = useState<File[]>([]);
  const [linkEditorOpen, setLinkEditorOpen] = useState(false);
  const [linkValue, setLinkValue] = useState('');
  const attachmentsRef = useRef<File[]>([]);
  const onChangeRef = useRef(onChange);

  useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  const emitValue = useCallback((editorInstance: Editor | null, nextAttachments: File[]) => {
    onChangeRef.current({
      text: editorInstance?.getText({ blockSeparator: '\n\n' }).trim() ?? '',
      html: editorInstance && !editorInstance.isEmpty ? editorInstance.getHTML() : '',
      attachments: nextAttachments,
    });
  }, []);

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
      }),
    ],
    content: '',
    editorProps: {
      attributes: {
        id,
        class:
          'min-h-44 px-4 py-3 text-sm leading-6 text-gray-100 outline-none [&_blockquote]:border-l-2 [&_blockquote]:border-cyan-400/40 [&_blockquote]:pl-3 [&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-lg [&_h2]:font-semibold [&_h3]:mb-1.5 [&_h3]:mt-3 [&_h3]:font-semibold [&_ol]:list-decimal [&_ol]:pl-5 [&_p]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5',
      },
    },
    onUpdate: ({ editor: updatedEditor }) => {
      emitValue(updatedEditor, attachmentsRef.current);
    },
  });

  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [disabled, editor]);

  useEffect(() => {
    if (!editor) return;
    editor.commands.clearContent();
    attachmentsRef.current = [];
    setAttachments([]);
    setLinkEditorOpen(false);
    setLinkValue('');
    emitValue(editor, []);
  }, [editor, emitValue, resetKey]);

  const updateAttachments = useCallback(
    (nextAttachments: File[]) => {
      attachmentsRef.current = nextAttachments;
      setAttachments(nextAttachments);
      emitValue(editor, nextAttachments);
    },
    [editor, emitValue],
  );

  const onDropAccepted = useCallback(
    (acceptedFiles: File[]) => {
      const uniqueFiles = [...attachmentsRef.current];
      for (const file of acceptedFiles) {
        const duplicate = uniqueFiles.some(
          (current) =>
            current.name === file.name
            && current.size === file.size
            && current.lastModified === file.lastModified,
        );
        if (!duplicate) uniqueFiles.push(file);
      }
      if (uniqueFiles.length > MAX_ATTACHMENTS) {
        toast.warning(t('adminCommunications.attachments.tooMany', { count: MAX_ATTACHMENTS }));
        return;
      }
      const totalBytes = uniqueFiles.reduce((sum, file) => sum + file.size, 0);
      if (totalBytes > MAX_ATTACHMENTS_BYTES) {
        toast.warning(t('adminCommunications.attachments.tooLarge'));
        return;
      }
      updateAttachments(uniqueFiles);
    },
    [t, updateAttachments],
  );

  const { getInputProps, getRootProps, isDragActive } = useDropzone({
    accept: ACCEPTED_ATTACHMENTS,
    disabled,
    maxFiles: MAX_ATTACHMENTS,
    maxSize: MAX_ATTACHMENTS_BYTES,
    multiple: true,
    onDropAccepted,
    onDropRejected: () => toast.warning(t('adminCommunications.attachments.rejected')),
  });

  const totalBytes = attachments.reduce((sum, file) => sum + file.size, 0);
  const toolbarDisabled = disabled || !editor;
  const applyLink = () => {
    if (!editor) return;
    const normalized = linkValue.trim();
    if (!/^(https?:\/\/|mailto:)/i.test(normalized)) {
      toast.warning(t('adminCommunications.editor.linkInvalid'));
      return;
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: normalized }).run();
    setLinkEditorOpen(false);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-white/[0.035] focus-within:border-cyan-400/30 focus-within:ring-2 focus-within:ring-cyan-400/10">
      <div className="flex flex-wrap items-center gap-1 border-b border-white/10 bg-black/10 px-2 py-1.5">
        <ToolbarButton
          label={t('adminCommunications.editor.bold')}
          active={editor?.isActive('bold')}
          disabled={toolbarDisabled}
          onClick={() => editor?.chain().focus().toggleBold().run()}
        >
          <Bold className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.italic')}
          active={editor?.isActive('italic')}
          disabled={toolbarDisabled}
          onClick={() => editor?.chain().focus().toggleItalic().run()}
        >
          <Italic className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.underline')}
          active={editor?.isActive('underline')}
          disabled={toolbarDisabled}
          onClick={() => editor?.chain().focus().toggleUnderline().run()}
        >
          <Underline className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.link')}
          active={editor?.isActive('link')}
          disabled={toolbarDisabled}
          onClick={() => {
            setLinkValue(String(editor?.getAttributes('link').href || ''));
            setLinkEditorOpen((value) => !value);
          }}
        >
          <LinkIcon className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.heading')}
          active={editor?.isActive('heading', { level: 2 })}
          disabled={toolbarDisabled}
          onClick={() => editor?.chain().focus().toggleHeading({ level: 2 }).run()}
        >
          <span className="text-xs font-bold">H2</span>
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.bullets')}
          active={editor?.isActive('bulletList')}
          disabled={toolbarDisabled}
          onClick={() => editor?.chain().focus().toggleBulletList().run()}
        >
          <List className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.numbered')}
          active={editor?.isActive('orderedList')}
          disabled={toolbarDisabled}
          onClick={() => editor?.chain().focus().toggleOrderedList().run()}
        >
          <ListOrdered className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.quote')}
          active={editor?.isActive('blockquote')}
          disabled={toolbarDisabled}
          onClick={() => editor?.chain().focus().toggleBlockquote().run()}
        >
          <Quote className="h-4 w-4" />
        </ToolbarButton>
        <span className="mx-1 h-5 w-px bg-white/10" />
        <ToolbarButton
          label={t('adminCommunications.editor.undo')}
          disabled={toolbarDisabled || !editor?.can().undo()}
          onClick={() => editor?.chain().focus().undo().run()}
        >
          <Undo2 className="h-4 w-4" />
        </ToolbarButton>
        <ToolbarButton
          label={t('adminCommunications.editor.redo')}
          disabled={toolbarDisabled || !editor?.can().redo()}
          onClick={() => editor?.chain().focus().redo().run()}
        >
          <Redo2 className="h-4 w-4" />
        </ToolbarButton>
      </div>

      {linkEditorOpen && (
        <div className="flex flex-wrap items-center gap-2 border-b border-white/10 bg-black/10 px-3 py-2">
          <input
            type="url"
            autoFocus
            value={linkValue}
            disabled={disabled}
            onChange={(event) => setLinkValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                applyLink();
              }
            }}
            placeholder={t('adminCommunications.editor.linkPlaceholder')}
            className="min-w-48 flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white placeholder:text-gray-600 focus:border-cyan-400/30 focus:outline-none"
          />
          {editor?.isActive('link') && (
            <button
              type="button"
              onClick={() => {
                editor.chain().focus().extendMarkRange('link').unsetLink().run();
                setLinkEditorOpen(false);
              }}
              className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-gray-300 hover:bg-white/10"
            >
              {t('adminCommunications.editor.removeLink')}
            </button>
          )}
          <button
            type="button"
            disabled={disabled || !linkValue.trim()}
            onClick={applyLink}
            className="rounded-lg bg-cyan-400 px-3 py-1.5 text-xs font-semibold text-slate-950 disabled:opacity-40"
          >
            {t('adminCommunications.editor.applyLink')}
          </button>
        </div>
      )}

      <EditorContent editor={editor} />

      <div className="border-t border-white/10 p-2.5">
        <div
          {...getRootProps()}
          className={`flex cursor-pointer items-center justify-between gap-3 rounded-lg border border-dashed px-3 py-2.5 text-xs transition ${
            isDragActive
              ? 'border-cyan-300/60 bg-cyan-400/10 text-cyan-200'
              : 'border-white/15 text-gray-400 hover:border-cyan-300/30 hover:bg-white/5 hover:text-gray-200'
          } ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
        >
          <input {...getInputProps()} />
          <span className="inline-flex min-w-0 items-center gap-2">
            <Paperclip className="h-4 w-4 shrink-0 text-cyan-300" />
            <span className="truncate">
              {isDragActive
                ? t('adminCommunications.attachments.drop')
                : t('adminCommunications.attachments.add')}
            </span>
          </span>
          <span className="shrink-0 text-[10px] text-gray-500">
            {attachments.length}/{MAX_ATTACHMENTS} · {formatBytes(totalBytes, i18n.language)}/15 MB
          </span>
        </div>

        {attachments.length > 0 && (
          <ul className="mt-2 grid gap-1.5 sm:grid-cols-2">
            {attachments.map((file) => (
              <li
                key={`${file.name}-${file.size}-${file.lastModified}`}
                className="flex min-w-0 items-center gap-2 rounded-lg bg-white/5 px-2.5 py-2 text-xs text-gray-300"
              >
                <FileText className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
                <span className="min-w-0 flex-1 truncate" title={file.name}>{file.name}</span>
                <span className="shrink-0 text-[10px] text-gray-500">
                  {formatBytes(file.size, i18n.language)}
                </span>
                <button
                  type="button"
                  aria-label={t('adminCommunications.attachments.remove', { name: file.name })}
                  disabled={disabled}
                  onClick={(event) => {
                    event.stopPropagation();
                    updateAttachments(
                      attachmentsRef.current.filter((current) => current !== file),
                    );
                  }}
                  className="rounded p-0.5 text-gray-500 hover:bg-white/10 hover:text-white"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
