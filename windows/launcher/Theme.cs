using System.Drawing;
using System.Windows.Forms;

namespace VillageLife;

/// <summary>Colors used by the launcher in one appearance mode.</summary>
internal sealed class ThemePalette {
    public Color Window { get; }
    public Color Control { get; }
    public Color Card { get; }
    public Color Field { get; }
    public Color Text { get; }
    public Color MutedText { get; }
    public Color Button { get; }
    public Color ButtonText { get; }
    public Color Accent { get; }
    public Color AccentText { get; }
    public Color Border { get; }
    public Color Info { get; }
    public Color InfoText { get; }
    public Color SelectedNav { get; }
    public Color NavText { get; }

    public ThemePalette(Color window, Color control, Color card, Color field,
                        Color text, Color mutedText, Color button, Color buttonText,
                        Color accent, Color accentText, Color border, Color info,
                        Color infoText, Color selectedNav, Color navText) {
        Window=window; Control=control; Card=card; Field=field; Text=text;
        MutedText=mutedText; Button=button; ButtonText=buttonText; Accent=accent;
        AccentText=accentText; Border=border; Info=info; InfoText=infoText;
        SelectedNav=selectedNav; NavText=navText;
    }
}

/// <summary>
/// Applies the current palette to an existing control tree. Dialogs call
/// Apply before ShowDialog so every custom window follows the saved mode.
/// </summary>
internal static class ThemeManager {
    public static bool Dark { get; private set; }
    public static ThemePalette Palette => Dark ? DarkPalette : LightPalette;

    public static readonly ThemePalette LightPalette = new(
        SystemColors.Window, SystemColors.Control, SystemColors.Window,
        SystemColors.Window, SystemColors.WindowText, SystemColors.GrayText,
        SystemColors.Control, SystemColors.ControlText, SystemColors.Highlight,
        SystemColors.HighlightText, SystemColors.ControlDark, SystemColors.Info,
        SystemColors.InfoText, SystemColors.Window, SystemColors.ControlText);

    public static readonly ThemePalette DarkPalette = new(
        Color.FromArgb(30,30,30), Color.FromArgb(37,37,38),
        Color.FromArgb(45,45,48), Color.FromArgb(56,56,60),
        Color.FromArgb(240,240,240), Color.FromArgb(170,170,170),
        Color.FromArgb(58,58,61), Color.FromArgb(240,240,240),
        Color.FromArgb(14,99,156), Color.White, Color.FromArgb(90,90,93),
        Color.FromArgb(58,51,32), Color.FromArgb(245,230,184),
        Color.FromArgb(58,58,61), Color.FromArgb(240,240,240));

    public static void SetDark(bool dark)=>Dark=dark;

    public static void Apply(Control root)=>ApplyControl(root,Role.Window);

    enum Role { Window, Control, Card, Field, Info }

    static Color Background(Role role)=>role switch {
        Role.Control=>Palette.Control,
        Role.Card=>Palette.Card,
        Role.Field=>Palette.Field,
        Role.Info=>Palette.Info,
        _=>Palette.Window
    };

    static void ApplyButton(Button button, Role role) {
        if (Equals(button.Tag,"primary")) {
            button.BackColor=Palette.Accent;
            button.ForeColor=Palette.AccentText;
            button.FlatAppearance.BorderColor=Palette.Accent;
        } else if (role==Role.Info) {
            button.BackColor=Palette.Info;
            button.ForeColor=Palette.InfoText;
            button.FlatAppearance.BorderColor=Palette.Border;
        } else {
            button.BackColor=Palette.Button;
            button.ForeColor=Palette.ButtonText;
            button.FlatAppearance.BorderColor=Palette.Border;
        }
        button.UseVisualStyleBackColor=false;
        button.FlatStyle=FlatStyle.Flat;
        button.FlatAppearance.BorderSize=1;
    }

    static void ApplyControl(Control control, Role parentRole) {
        var role=parentRole;
        if (control is Form) role=Role.Window;
        else if (control.AccessibleName=="Navigation") role=Role.Control;
        else if (control.AccessibleName=="Action required") role=Role.Info;
        else if (control is TableLayoutPanel table && table.BorderStyle==BorderStyle.FixedSingle) role=Role.Card;

        switch (control) {
            case Label label:
                label.ForeColor=role==Role.Info ? Palette.InfoText
                    : Equals(label.Tag,"muted") ? Palette.MutedText : Palette.Text;
                label.BackColor=Color.Transparent;
                break;
            case Button button:
                ApplyButton(button,role);
                break;
            case CheckBox check:
                check.ForeColor=role==Role.Info ? Palette.InfoText : Palette.Text;
                check.BackColor=Background(role);
                check.FlatStyle=Dark ? FlatStyle.Flat : FlatStyle.Standard;
                break;
            case RadioButton radio:
                radio.ForeColor=role==Role.Info ? Palette.InfoText : Palette.Text;
                radio.BackColor=Background(role);
                radio.FlatStyle=Dark ? FlatStyle.Flat : FlatStyle.Standard;
                break;
            case TextBoxBase text:
                text.BackColor=Palette.Field;
                text.ForeColor=Palette.Text;
                text.BorderStyle=BorderStyle.FixedSingle;
                break;
            case ListBox list:
                list.BackColor=Palette.Field;
                list.ForeColor=Palette.Text;
                list.BorderStyle=BorderStyle.FixedSingle;
                break;
            case ComboBox combo:
                combo.BackColor=Palette.Field;
                combo.ForeColor=Palette.Text;
                combo.FlatStyle=FlatStyle.Flat;
                break;
            case ProgressBar bar:
                bar.BackColor=Palette.Control;
                bar.ForeColor=Palette.Accent;
                break;
            case PictureBox picture:
                picture.BackColor=Background(role);
                break;
            case Panel panel:
                panel.BackColor=Background(role);
                panel.ForeColor=role==Role.Info ? Palette.InfoText : Palette.Text;
                break;
            case Form form:
                form.BackColor=Palette.Window;
                form.ForeColor=Palette.Text;
                break;
        }
        foreach (Control child in control.Controls) ApplyControl(child,role);
    }
}
