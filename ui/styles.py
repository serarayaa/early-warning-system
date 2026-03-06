def inject_css(st):
    st.markdown(
        """
        <style>
        /* ancho y padding */
        .block-container { padding-top: 2.0rem; padding-bottom: 2.0rem; }

        /* títulos */
        h1, h2, h3 { letter-spacing: -0.5px; }

        /* cards (contenedores) */
        .ews-card {
            background: rgba(17, 24, 39, 0.9);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 18px 18px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.35);
        }

        /* divider */
        .ews-divider { height: 1px; background: rgba(255,255,255,0.08); margin: 18px 0; }

        /* badges */
        .ews-badge {
            display:inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 12px;
            border: 1px solid rgba(255,255,255,0.12);
            background: rgba(255,255,255,0.04);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )