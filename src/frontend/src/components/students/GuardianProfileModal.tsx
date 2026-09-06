import { useState, useEffect, useCallback, useRef } from 'react';
import { X, Save, Sparkles, AlertTriangle, Check } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import api, { extractError } from '../../lib/api';
import { httpStatusOf } from '../../lib/httpErrors';
import type { User, GuardianProfile, TemplateInfo } from '../../types';
import { Button } from '../ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

interface GuardianProfileModalProps {
    isOpen: boolean;
    onClose: () => void;
    student: User | null;
}

const PROFILE_TABS = ['general', 'persona', 'safety'] as const;
type Tab = (typeof PROFILE_TABS)[number];

export function GuardianProfileModal({ isOpen, onClose, student }: GuardianProfileModalProps) {
    const { t } = useTranslation(['students', 'common']);
    const [loading, setLoading] = useState(false);
    const [templates, setTemplates] = useState<TemplateInfo[]>([]);
    const [profile, setProfile] = useState<Partial<GuardianProfile>>({});
    const [selectedTemplate, setSelectedTemplate] = useState<string>('');
    const [activeTab, setActiveTab] = useState<Tab>('general');
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const requestRef = useRef(0);

    const loadData = useCallback(async () => {
        if (!student) return;
        const requestId = ++requestRef.current;
        setLoading(true);
        setError(null);
        // Clear any success state left by a previous student: reopening the
        // modal for another student must not keep showing the old toast text.
        setSuccess(null);
        try {
            // Load templates
            const templatesRes = await api.get('/guardian-profiles/templates');
            if (requestId !== requestRef.current) return;
            setTemplates(templatesRes.data);

            // Load existing profile
            try {
                const profileRes = await api.get(`/guardian-profiles/students/${student.id}`);
                if (requestId !== requestRef.current) return;
                setProfile(profileRes.data);
                setSelectedTemplate(profileRes.data.template_name);
            } catch (error: unknown) {
                if (requestId !== requestRef.current) return;
                const status = httpStatusOf(error);
                if (status === 404) {
                    // No profile yet, use default
                    setProfile({});
                    setSelectedTemplate('default');
                } else {
                    throw error;
                }
            }
        } catch {
            if (requestId === requestRef.current) {
                setError(t('students:errors.profileLoadFailed'));
            }
        } finally {
            if (requestId === requestRef.current) {
                setLoading(false);
            }
        }
    }, [student, t]);

    const closeModal = useCallback(() => {
        requestRef.current += 1;
        setLoading(false);
        setSuccess(null);
        onClose();
    }, [onClose]);

    useEffect(() => {
        if (!isOpen || !success) return;
        const timeoutId = setTimeout(closeModal, 1500);
        return () => clearTimeout(timeoutId);
    }, [isOpen, closeModal, success]);

    useEffect(() => {
        // Invalidate the previous student's requests before clearing the form,
        // so a late profile response cannot repopulate this modal.
        requestRef.current += 1;
        setLoading(false);
        setError(null);
        setSuccess(null);
        setProfile({});
        setSelectedTemplate('');
        setActiveTab('general');
        if (!isOpen || !student) return;
        void loadData();
        return () => {
            requestRef.current += 1;
        };
    }, [isOpen, student, loadData]);

    const handleSave = async () => {
        if (!student) return;
        const requestId = ++requestRef.current;
        const studentId = student.id;
        setLoading(true);
        setError(null);
        setSuccess(null);

        try {
            const data = {
                ...profile,
                template_name: selectedTemplate
            };

            if (profile.id) {
                await api.put(`/guardian-profiles/students/${studentId}`, data);
            } else {
                await api.post(`/guardian-profiles/students/${studentId}`, data);
            }
            if (requestId === requestRef.current) {
                setSuccess(t('students:success.saved'));
            }
        } catch (error: unknown) {
            if (requestId === requestRef.current) {
                setError(extractError(error, t('students:errors.saveFailed')));
            }
        } finally {
            if (requestId === requestRef.current) {
                setLoading(false);
            }
        }
    };

    if (!isOpen) return null;

    return (
        <Dialog open={isOpen} onOpenChange={(open) => { if (!open) closeModal(); }}>
            <DialogContent
                showCloseButton={false}
                className="max-w-md p-0 max-h-[90vh] overflow-hidden"
            >
                {/* Header */}
                <DialogHeader className="flex-row items-center justify-between p-6 border-b border-border">
                    <DialogTitle className="text-xl font-bold flex items-center gap-2">
                        <Sparkles className="w-5 h-5 text-indigo-500" />
                        {t('students:guardianProfile')}: {student?.display_name}
                    </DialogTitle>
                    <button onClick={closeModal} className="p-2 hover:bg-muted rounded-full" aria-label={t('common:close')}><X className="w-6 h-6" /></button>
                </DialogHeader>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                    {/* Tabs */}
                    <div className="flex gap-2 mb-6 border-b border-border">
                        {PROFILE_TABS.map(tab => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-4 py-2 font-medium border-b-2 transition-colors ${activeTab === tab
                                        ? 'border-brand text-brand'
                                        : 'border-transparent text-muted-foreground hover:text-foreground'
                                    }`}
                            >
                                {t(`tabs.${tab}`, tab.charAt(0).toUpperCase() + tab.slice(1))}
                            </button>
                        ))}
                    </div>

                    {loading && <div className="text-center py-8">{t('students:loading')}</div>}

                    {!loading && activeTab === 'general' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:template')}</label>
                                <Select
                                    value={selectedTemplate}
                                    onValueChange={(value) => setSelectedTemplate(value ?? selectedTemplate)}
                                    items={templates.map((tpl) => ({ value: tpl.name, label: tpl.display_name }))}
                                >
                                    <SelectTrigger aria-label={t('students:template')} className="w-full">
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {templates.map(tpl => (
                                            <SelectItem key={tpl.name} value={tpl.name}>{tpl.display_name}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {templates.find(t => t.name === selectedTemplate)?.description}
                                </p>
                            </div>

                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label htmlFor="age" className="block text-sm font-medium mb-1">{t('students:age')}</label>
                                    <input
                                        id="age"
                                        type="number"
                                        value={profile.age || ''}
                                        onChange={e => setProfile({ ...profile, age: parseInt(e.target.value) || undefined })}
                                        className="w-full p-2 border border-border rounded-lg bg-surface-hover"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="gender" className="block text-sm font-medium mb-1">{t('students:gender')}</label>
                                    <select
                                        id="gender"
                                        value={profile.gender || ''}
                                        onChange={e => setProfile({ ...profile, gender: e.target.value })}
                                        className="w-full p-2 border border-border rounded-lg bg-surface-hover"
                                    >
                                        <option value="">{t('students:select')}</option>
                                        <option value="male">{t('students:male')}</option>
                                        <option value="female">{t('students:female')}</option>
                                        <option value="non-binary">{t('students:nonBinary')}</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                    )}

                    {!loading && activeTab === 'persona' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:companionName')}</label>
                                <input
                                    type="text"
                                    value={profile.companion_persona?.name || ''}
                                    onChange={e => setProfile({
                                        ...profile,
                                        companion_persona: { ...profile.companion_persona, name: e.target.value }
                                    })}
                                    className="w-full p-2 border border-border rounded-lg bg-surface-hover"
                                    placeholder={t('placeholders.companionName')}
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:role')}</label>
                                <input
                                    type="text"
                                    value={profile.companion_persona?.role || ''}
                                    onChange={e => setProfile({
                                        ...profile,
                                        companion_persona: { ...profile.companion_persona, role: e.target.value }
                                    })}
                                    className="w-full p-2 border border-border rounded-lg bg-surface-hover"
                                    placeholder={t('placeholders.role')}
                                />
                            </div>
                        </div>
                    )}

                    {!loading && activeTab === 'safety' && (
                        <div className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium mb-1">{t('students:contentFilterLevel')}</label>
                                <select
                                    value={profile.safety_constraints?.content_filter_level || 'default'}
                                    onChange={e => setProfile({
                                        ...profile,
                                        safety_constraints: {
                                            ...profile.safety_constraints,
                                            content_filter_level: e.target.value === 'default' ? undefined : e.target.value
                                        }
                                    })}
                                    className="w-full p-2 border border-border rounded-lg bg-surface-hover"
                                >
                                    <option value="">{t('students:triStateDefault')}</option>
                                    <option value="strict">{t('students:strict')}</option>
                                    <option value="standard">{t('students:standard')}</option>
                                    <option value="relaxed">{t('students:relaxed')}</option>
                                </select>
                            </div>

                            <div>
                                <label htmlFor="forbidden-topics" className="block text-sm font-medium mb-1">{t('students:forbiddenTopics')}</label>
                                <textarea
                                    id="forbidden-topics"
                                    rows={3}
                                    value={(profile.safety_constraints?.forbidden_topics ?? []).join('\n')}
                                    onChange={e => {
                                        const terms = e.target.value.split('\n').map(s => s.trim()).filter(Boolean);
                                        setProfile({
                                            ...profile,
                                            safety_constraints: { ...profile.safety_constraints, forbidden_topics: terms }
                                        });
                                    }}
                                    placeholder="astronomía"
                                    className="w-full p-2 border border-border rounded-lg bg-surface-hover font-mono text-sm"
                                />
                                <p className="text-xs text-muted-foreground mt-1">{t('students:forbiddenTopicsHelp')}</p>
                            </div>

                            <div>
                                <label htmlFor="trigger-words" className="block text-sm font-medium mb-1">{t('students:triggerWords')}</label>
                                <textarea
                                    id="trigger-words"
                                    rows={3}
                                    value={(profile.safety_constraints?.trigger_words ?? []).join('\n')}
                                    onChange={e => {
                                        const terms = e.target.value.split('\n').map(s => s.trim()).filter(Boolean);
                                        setProfile({
                                            ...profile,
                                            safety_constraints: { ...profile.safety_constraints, trigger_words: terms }
                                        });
                                    }}
                                    placeholder="guerra"
                                    className="w-full p-2 border border-border rounded-lg bg-surface-hover font-mono text-sm"
                                />
                                <p className="text-xs text-muted-foreground mt-1">{t('students:triggerWordsHelp')}</p>
                            </div>

                            <div>
                                <label htmlFor="max-response-length" className="block text-sm font-medium mb-1">{t('students:maxResponseLength')}</label>
                                <input
                                    id="max-response-length"
                                    type="number"
                                    min={0}
                                    value={profile.safety_constraints?.max_response_length ?? ''}
                                    onChange={e => setProfile({
                                        ...profile,
                                        safety_constraints: {
                                            ...profile.safety_constraints,
                                            // <=0 clears the cap (sent as
                                            // undefined): the backend rejects
                                            // 0 because it corrupts feedback.
                                            max_response_length:
                                              e.target.value !== '' &&
                                              Number(e.target.value) > 0
                                                ? Number(e.target.value)
                                                : undefined
                                        }
                                    })}
                                    className="w-full p-2 border border-border rounded-lg bg-surface-hover"
                                />
                                <p className="text-xs text-muted-foreground mt-1">{t('students:maxResponseLengthHelp')}</p>
                            </div>

                            <div className="space-y-2">
                                <div>
                                    <span className="block text-sm font-medium">{t('students:featureGates')}</span>
                                    <p className="text-xs text-muted-foreground mt-0.5">{t('students:featureGatesHelp')}</p>
                                </div>
                                {([
                                    ['block_ai_chat', 'blockChat'],
                                    ['block_board_ai', 'blockBoardAI'],
                                    ['block_custom_topics', 'blockCustomTopics'],
                                    ['block_autogen_pictograms', 'blockAutogen'],
                                    ['block_social_messaging', 'blockSocial'],
                                ] as const).map(([key, labelKey]) => {
                                    const value = profile.safety_constraints?.[key];
                                    return (
                                        <div key={key} className="flex items-center justify-between gap-2 text-sm">
                                            <span className="text-foreground">{t(`students:${labelKey}`)}</span>
                                            <select
                                                value={value === undefined ? 'default' : value ? 'true' : 'false'}
                                                onChange={e => setProfile({
                                                    ...profile,
                                                    safety_constraints: {
                                                        ...profile.safety_constraints,
                                                        [key]: e.target.value === 'default' ? undefined : e.target.value === 'true'
                                                    }
                                                })}
                                                className="w-36 p-2 border border-border rounded-lg bg-surface-hover text-sm"
                                            >
                                                <option value="default">{t('students:triStateDefault')}</option>
                                                <option value="true">{t('students:triStateOn')}</option>
                                                <option value="false">{t('students:triStateOff')}</option>
                                            </select>
                                        </div>
                                    );
                                })}
                            </div>

                            <div className="flex items-start gap-2 text-sm">
                                <span className="text-foreground">{t('students:sentinel')}</span>
                                <select
                                    value={profile.safety_constraints?.sentinel_moderation === undefined ? 'default' : profile.safety_constraints.sentinel_moderation ? 'true' : 'false'}
                                    onChange={e => setProfile({
                                        ...profile,
                                        safety_constraints: {
                                            ...profile.safety_constraints,
                                            sentinel_moderation: e.target.value === 'default' ? undefined : e.target.value === 'true'
                                        }
                                    })}
                                    className="w-36 p-2 border border-border rounded-lg bg-surface-hover text-sm ml-auto"
                                >
                                    <option value="default">{t('students:triStateDefault')}</option>
                                    <option value="true">{t('students:triStateOn')}</option>
                                    <option value="false">{t('students:triStateOff')}</option>
                                </select>
                            </div>
                            <p className="text-xs text-muted-foreground -mt-2">{t('students:sentinelHelp')}</p>
                        </div>
                    )}

                    {error && (
                        <div className="mt-4 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg flex items-center gap-2">
                            <AlertTriangle className="w-5 h-5" />
                            {error}
                        </div>
                    )}
                    {success && (
                        <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 text-green-600 dark:text-green-400 rounded-lg flex items-center gap-2">
                            <Check className="w-5 h-5" />
                            {success}
                        </div>
                    )}

                </div>

                {/* Footer */}
                <div className="p-6 border-t border-border flex justify-end gap-3">
                    <button
                        onClick={closeModal}
                        className="px-4 py-2 text-muted-foreground hover:bg-muted rounded-lg"
                    >
                        {t('students:cancel')}
                    </button>
                    <Button onClick={handleSave} disabled={loading} className="flex items-center gap-2" >
                        <Save className="w-4 h-4" />
                        {t('save')}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
