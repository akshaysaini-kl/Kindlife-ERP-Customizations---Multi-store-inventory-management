// ─── B2B / B2C Channel Badge ────────────────────────────────────────────────
// Proven pattern: jQuery $(function) + exact Frappe navbar selector
$(function () {
    const CHANNEL_KEY = "kl_active_channel";

    // ── Helpers ──────────────────────────────────────────────────────────────
    function getBadgeProps(channel) {
        if (channel === "B2B") return { label: "B2B", cls: "kl-badge-b2b" };
        if (channel === "B2C") return { label: "B2C", cls: "kl-badge-b2c" };
        return { label: "B2B &amp; B2C", cls: "kl-badge-both" };
    }

    function injectBadge(channel, isBoth) {
        $("#kl-channel-badge").remove();
        const { label, cls } = getBadgeProps(channel);
        const arrow = isBoth ? ' <span class="kl-badge-arrow">&#9660;</span>' : "";
        const clickCls = isBoth ? " kl-badge-clickable" : "";

        const badge = $(`<li id="kl-channel-badge" class="nav-item kl-channel-badge-wrapper">
            <span class="kl-channel-badge ${cls}${clickCls}">${label}${arrow}</span>
        </li>`);

        if (isBoth) {
            badge.find(".kl-channel-badge").on("click", function () {
                showChannelSelector(channel);
            });
        }

        $("header.navbar > .container > .navbar-collapse > ul").prepend(badge);
    }

    // ── Channel selector dialog ───────────────────────────────────────────────
    function showChannelSelector(current) {
        const d = new frappe.ui.Dialog({
            title: __("Select Active Channel"),
            fields: [{
                fieldtype: "Select",
                fieldname: "channel",
                label: __("View As"),
                options: ["Both", "B2B", "B2C"],
                default: current || "Both"
            }],
            primary_action_label: __("Apply"),
            primary_action(values) {
                const selected = values.channel;
                localStorage.setItem(CHANNEL_KEY, selected);
                injectBadge(selected, true);
                applyChannelFilter(selected);
                d.hide();
            }
        });
        d.show();
    }

    // ── Apply list-view filter via cur_list ───────────────────────────────────
    // Only these doctypes have the custom_type field
    const TYPED_DOCTYPES = new Set([
        "Supplier", "Purchase Order", "Purchase Receipt", "Purchase Invoice",
        "Stock Entry", "Sales Order", "Pick List", "Delivery Note",
        "Consolidated Pick List", "Sales Invoice", "Warehouse"
    ]);

    function applyChannelFilter(channel) {
        // Resolve passed channel or read from storage
        const ch = channel !== undefined ? channel : localStorage.getItem(CHANNEL_KEY);
        if (!ch) return;

        setTimeout(function () {
            // cur_list is Frappe's global for the active list view instance
            if (typeof cur_list === "undefined" || !cur_list || !cur_list.filter_area) return;

            // Skip if this doctype doesn't have custom_type
            if (!TYPED_DOCTYPES.has(cur_list.doctype)) return;

            const filter_list = cur_list.filter_area.filter_list;

            // Remove any existing custom_type filter
            const to_remove = (filter_list.filters || []).filter(
                f => f.fieldname === "custom_type"
            );
            to_remove.forEach(f => f.remove());

            if (ch !== "Both") {
                // Add channel filter then let it auto-refresh
                cur_list.filter_area.add([[cur_list.doctype, "custom_type", "=", ch]]);
            } else {
                // No channel filter – refresh list to show all records
                cur_list.refresh();
            }
        }, 500);
    }

    // ── Bootstrap ─────────────────────────────────────────────────────────────
    frappe.call({
        method: "kindlife_app.services.permissions.base.get_current_user_type",
        callback: function (r) {
            if (!r || !r.message) return;

            const userType = r.message; // "B2B", "B2C", or "Both"
            const isBoth = (userType === "Both");

            // Restore last session selection (only relevant if they have Both access)
            const activeChannel = isBoth
                ? (localStorage.getItem(CHANNEL_KEY) || "Both")
                : userType;

            injectBadge(activeChannel, isBoth);

            if (isBoth) {
                // Apply filter on every page navigation
                $(document).on("page-change", function () {
                    applyChannelFilter();
                });
            }
        }
    });
});
// ────────────────────────────────────────────────────────────────────────────




document.addEventListener("DOMContentLoaded", () => {
    const setLinkAttributes = () => {
        // console.log("Setting attributes for Doctype links...");

        document.querySelectorAll('a[title="Open Link"]').forEach((link) => {
            if (!link.hasAttribute("target")) {
                link.setAttribute("target", "_blank");
                link.setAttribute("rel", "noopener noreferrer");
            }
        });

        document.querySelectorAll('.dt-cell__content a[data-doctype]').forEach((link) => {
            if (!link.hasAttribute("target")) {
                link.setAttribute("target", "_blank");
                link.setAttribute("rel", "noopener noreferrer");
            }
        });
    };

    // Run on initial load
    setLinkAttributes();

    // Watch for future DOM changes
    const observer = new MutationObserver(setLinkAttributes);

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
});



frappe.ui.form.Factory.prototype.make = function(route) {
	const me = this;
    console.log("---")
	// Call the original make method
	const original_make = frappe.ui.form.Factory.prototype._original_make || frappe.ui.form.Factory.prototype.make;
	if (!frappe.ui.form.Factory.prototype._original_make) {
		frappe.ui.form.Factory.prototype._original_make = original_make;
	}

	original_make.call(this, route);

	// Wait a bit and apply full-width
	const interval = setInterval(() => {
		const current_form = frappe?.container?.page?.form;
		if (current_form && current_form.page) {
			current_form.page.toggle_full_width(true);
			clearInterval(interval);
		}
	}, 200);
};