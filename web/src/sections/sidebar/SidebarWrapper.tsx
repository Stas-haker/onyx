import React, { useMemo } from "react";
import { cn } from "@/lib/utils";
import { Button, Text } from "@opal/components";
import { SvgSidebar } from "@opal/icons";

interface LogoSectionProps {
  folded?: boolean;
  onFoldClick?: () => void;
}

function LogoSection({ folded, onFoldClick }: LogoSectionProps) {
  const logo = useMemo(
    () => (
      <div className="px-1 flex flex-col" aria-label="Miratorg">
        <Text font="heading-h3" color="text-05">
          {folded ? "M" : "Miratorg"}
        </Text>
        {!folded && (
          <Text font="secondary-body" color="text-03">
            Powered by Onyx
          </Text>
        )}
      </div>
    ),
    [folded]
  );
  const closeButton = useMemo(
    () => (
      <div className="px-1">
        <Button
          icon={SvgSidebar}
          prominence="tertiary"
          tooltip={folded ? "Open Sidebar" : "Close Sidebar"}
          tooltipSide={folded ? "right" : "bottom"}
          size="md"
          onClick={onFoldClick}
        />
      </div>
    ),
    [folded, onFoldClick]
  );

  return (
    <div className="flex flex-row justify-between items-start pt-3 px-2">
      {folded === undefined ? (
        logo
      ) : folded ? (
        <>
          <div className="group-hover/SidebarWrapper:hidden">{logo}</div>
          <div className="hidden group-hover/SidebarWrapper:flex">
            {closeButton}
          </div>
        </>
      ) : (
        <>
          {logo}
          {closeButton}
        </>
      )}
    </div>
  );
}

export interface SidebarWrapperProps {
  folded?: boolean;
  onFoldClick?: () => void;
  children?: React.ReactNode;
}

export default function SidebarWrapper({
  folded,
  onFoldClick,
  children,
}: SidebarWrapperProps) {
  return (
    // This extra `div` wrapping needs to be present (for some reason).
    // Without, the widths of the sidebars don't properly get set to the explicitly declared widths (i.e., `4rem` folded and `15rem` unfolded).
    <div>
      <div
        className={cn(
          "h-screen flex flex-col bg-background-tint-02 py-2 gap-4 group/SidebarWrapper transition-width duration-200 ease-in-out",
          folded ? "w-[3.25rem]" : "w-[15rem]"
        )}
      >
        <LogoSection folded={folded} onFoldClick={onFoldClick} />
        {children}
      </div>
    </div>
  );
}
