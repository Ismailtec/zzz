/** @odoo-module **/

import {ColorPickerField} from "@web/views/fields/color_picker/color_picker_field";
import {ColorList} from "@web/core/colorlist/colorlist";
import {patch} from "@web/core/utils/patch";
import {_t} from "@web/core/l10n/translation";

// Patch ColorPickerField.RECORD_COLORS (so picker shows 36 colors)
patch(ColorPickerField, {
    RECORD_COLORS: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35]
});

// Patch ColorList.COLORS (so tooltips work for all 36 colors)
patch(ColorList, {
    COLORS: [
        _t("No color"), _t("Red"), _t("Orange"), _t("Yellow"), _t("Cyan"), _t("Purple"),
        _t("Almond"), _t("Teal"), _t("Blue"), _t("Raspberry"), _t("Green"), _t("Violet"),
        _t("Dark red"), _t("Crimson"), _t("Light red"), _t("Navy blue"), _t("Royal blue"),
        _t("Sky blue"), _t("Dark green"), _t("Forest green"), _t("Light green"),
        _t("Dark orange"), _t("Gold"), _t("Light yellow"), _t("Indigo"), _t("Blue violet"),
        _t("Lavender"), _t("Dark brown"), _t("Brown"), _t("Tan"), _t("Dark gray"),
        _t("Gray"), _t("Light gray"), _t("Black"), _t("White"), _t("Pink")
    ]
});