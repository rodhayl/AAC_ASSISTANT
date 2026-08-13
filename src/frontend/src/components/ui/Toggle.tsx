interface ToggleProps {
  id?: string;
  name?: string;
  checked: boolean;
  label?: string;
  onChange: (checked: boolean) => void;
}

/** Shared accessible switch toggle (visually-hidden checkbox + styled track). */
export function Toggle({ id, name, checked, label, onChange }: ToggleProps) {
  return (
    <label className="relative inline-flex items-center cursor-pointer">
      <input
        id={id}
        name={name}
        type="checkbox"
        className="sr-only peer"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        aria-label={label}
      />
      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600" />
    </label>
  );
}
