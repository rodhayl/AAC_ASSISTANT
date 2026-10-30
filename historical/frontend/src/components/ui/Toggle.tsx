import { Switch } from './switch';

interface ToggleProps {
  id?: string;
  name?: string;
  checked: boolean;
  label?: string;
  onChange: (checked: boolean) => void;
}

/**
 * Shared accessible switch. Wraps the shadcn/Base UI Switch primitive while
 * keeping the legacy boolean-`onChange` prop shape, so existing call sites
 * stay unchanged. Size classes reproduce the previous 44x24 track + 20px knob.
 */
export function Toggle({ id, name, checked, label, onChange }: ToggleProps) {
  return (
    <Switch
      id={id}
      name={name}
      checked={checked}
      onCheckedChange={(value) => onChange(Boolean(value))}
      aria-label={label}
      className="h-6 w-11 [&_[data-slot=switch-thumb]]:h-5 [&_[data-slot=switch-thumb]]:w-5"
    />
  );
}
