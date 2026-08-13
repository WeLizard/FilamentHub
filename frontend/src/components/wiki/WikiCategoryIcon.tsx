import type { ComponentType } from 'react';
import {
  BookOpen,
  Box,
  Boxes,
  Calculator,
  CircleHelp,
  Cog,
  Compass,
  Cpu,
  FileText,
  GraduationCap,
  Hammer,
  Laptop,
  Layers,
  Lightbulb,
  Package,
  PackageOpen,
  Rocket,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Store,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

import { FilamentSpoolIcon } from '../icons/FilamentSpoolIcon';
import { LayeredPrinterIcon } from '../icons/LayeredPrinterIcon';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import PrinterIcon from '../icons/PrinterIcon';
import RetractIcon from '../icons/RetractIcon';
import { SpoolIcon } from '../icons/SpoolIcon';

type WikiIconComponent = ComponentType<{ className?: string }>;

const FullSpoolIcon: WikiIconComponent = ({ className }) => (
  <SpoolIcon pct={100} className={className} />
);

const lucideIcons: Record<string, LucideIcon> = {
  BookOpen,
  Box,
  Boxes,
  Calculator,
  CircleHelp,
  Cog,
  Compass,
  Cpu,
  FileText,
  GraduationCap,
  Hammer,
  Laptop,
  Layers,
  Lightbulb,
  Package,
  PackageOpen,
  Rocket,
  Settings,
  SlidersHorizontal,
  Sparkles,
  Store,
  Wrench,
};

const customIcons: Record<string, WikiIconComponent> = {
  FilamentSpool: FilamentSpoolIcon,
  FilamentSpoolIcon,
  LayeredPrinter: LayeredPrinterIcon,
  LayeredPrinterIcon,
  Printer3D: Printer3DIcon,
  Printer3DIcon,
  Printer: Printer3DIcon,
  PrinterIcon,
  Retract: RetractIcon,
  RetractIcon,
  Spool: FullSpoolIcon,
  SpoolIcon: FullSpoolIcon,
};

const legacyIconAliases: Record<string, WikiIconComponent> = {
  '🧵': FilamentSpoolIcon,
  '🔧': Wrench,
  '🎓': GraduationCap,
  '🚀': Rocket,
  '💻': Laptop,
  '📄': FileText,
};

export function resolveWikiCategoryIcon(name: string | null): WikiIconComponent {
  if (!name) return BookOpen;
  return customIcons[name] ?? lucideIcons[name] ?? legacyIconAliases[name] ?? BookOpen;
}

export function WikiCategoryIcon({ name, className }: { name: string | null; className?: string }) {
  const Icon = resolveWikiCategoryIcon(name);
  return <Icon className={className} />;
}
